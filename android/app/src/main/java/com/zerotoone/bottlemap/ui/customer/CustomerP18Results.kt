
package com.zerotoone.bottlemap.ui.customer

import android.Manifest
import androidx.activity.compose.BackHandler
import androidx.compose.runtime.DisposableEffect
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import android.app.Activity
import android.content.Context
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.AndroidNearbyLocationSource
import com.zerotoone.bottlemap.data.distanceMeters
import com.zerotoone.bottlemap.data.Repositories
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.CustomerDiscoverySource
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.MatchedProductDto
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import com.zerotoone.bottlemap.network.SearchResultDto
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import com.zerotoone.bottlemap.ui.common.servingDisplayLabel
import com.zerotoone.bottlemap.ui.common.BmIconId
import com.zerotoone.bottlemap.ui.common.GlassFillLoading
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.delay
import kotlin.math.roundToInt
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

/** Reject only backend-confirmed query input failures; do not relabel network faults. */
internal fun p18QueryValidationCode(error:Exception):String? =
    (error as? BottleMapApiException)
        ?.takeIf{it.code=="VALIDATION_FAILED"}
        ?.fieldErrors?.firstOrNull{
            it.path=="query" && it.code in setOf(
                "MISSING","BLANK","STRING_TOO_LONG","NOT_SEARCHABLE")
        }?.code

internal sealed interface P18SearchState {
    data object Loading : P18SearchState
    data class Ready(val response: SearchBarsResponseDto) : P18SearchState
    data class InvalidQuery(val fieldCode:String) : P18SearchState
    data class Error(val message: String) : P18SearchState
}

internal class P18SearchViewModel(
    private val repository:CustomerDiscoverySource=Repositories.customer,
) : ViewModel() {
    private val mutable = MutableStateFlow<P18SearchState>(P18SearchState.Loading)
    val state = mutable.asStateFlow()
    private var job: Job? = null
    private var version = 0L
    private var lastKey: String? = null
    private var activeQuery:String? = null
    // Keep the full brand candidate list independently of selected-product responses.
    private val _suggestions = MutableStateFlow<SearchBarsResponseDto?>(null)
    val suggestions = _suggestions.asStateFlow()
    private val mutableBarTags=MutableStateFlow<Map<String,List<String>>>(emptyMap())
    val barTags=mutableBarTags.asStateFlow()
    private val tagRequests=mutableSetOf<String>()
    fun loadBarTags(id:String) {
        if(id.isBlank() || !tagRequests.add(id))return
        viewModelScope.launch {
            try {
                val detail=Repositories.customer.getPublishedBarMenu(id)
                if(detail.barId==id)mutableBarTags.value=
                    mutableBarTags.value+(id to detail.tags.take(2))
            } catch(cancelled:CancellationException){throw cancelled}
            catch(_:Exception){ /* Tag metadata is optional; don't block results. */ }
        }
    }
    // The result destination's ViewModel survives a detail push/pop.
    private val _location = MutableStateFlow<NearbyCoordinate?>(null)
    val location = _location.asStateFlow()
    fun setLocation(value: NearbyCoordinate) { if (value.isValid()) _location.value = value }
    fun clearLocation() { _location.value = null }
    fun load(query: String?, productId: String?, source: String,
             location: NearbyCoordinate? = null, force: Boolean = false) {
        // Never reuse candidates from a different search term. A product-id
        // follow-up intentionally preserves the original brand candidates.
        if(productId==null && !query.isNullOrBlank() && activeQuery!=query) {
            activeQuery=query
            _suggestions.value=null
        }
        val key = listOf(query, productId, source, location?.latitude, location?.longitude).joinToString("|")
        if (!force && key == lastKey) return
        lastKey=key
        job?.cancel()
        val request = ++version
        mutable.value = P18SearchState.Loading
        job=viewModelScope.launch {
            try {
                val result=repository.searchProduct(
                    query=query,productId=productId,source=source,
                    latitude=location?.latitude,longitude=location?.longitude,
                )
                if (request==version) {
                    if (query != null && productId == null) {
                        // Retain even a legitimate empty match; never fall back
                        // to an unrelated product-id response as "unknown whisky".
                        _suggestions.value = result
                    }
                    mutable.value=P18SearchState.Ready(result)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if(request==version) {
                    val invalid=p18QueryValidationCode(error)
                    mutable.value=if(invalid!=null)
                        P18SearchState.InvalidQuery(invalid)
                    else P18SearchState.Error(
                        "연결을 확인하고 다시 시도해 주세요.")
                }
            }
        }
    }
    fun retry() { lastKey=null }
}

/**
 * The query that opened this destination owns its candidate response.
 * Stale ViewModel data from a previous route or a productId lookup may never
 * be interpreted as the current query's "unrecognized whisky" response.
 */
internal fun p18OriginalResponse(
    query:String?,productId:String?,
    candidates:SearchBarsResponseDto?,latest:SearchBarsResponseDto?,
):SearchBarsResponseDto? = when {
    query!=null -> candidates?.takeIf{it.query==query}
        ?:latest?.takeIf{it.query==query}
    productId!=null -> latest?.takeIf{
        it.matchType=="product" || it.matchType=="none"
    }
    else -> null
}

/** Product-specific results may never take the place of brand candidates. */
internal fun p18ResolvedResult(
    chosenId:String?,initialProductId:String?,canSkip:Boolean,
    original:SearchBarsResponseDto?,latest:SearchBarsResponseDto?,
):SearchBarsResponseDto? = when {
    chosenId!=null -> latest?.takeIf {
        it.matchType=="product" &&
            it.matchedProducts.any{product->product.productId==chosenId}
    }
    initialProductId!=null -> latest?.takeIf {
        it.matchType=="product" &&
            it.matchedProducts.any{product->product.productId==initialProductId}
    }
    canSkip -> original
    else -> null
}

internal enum class P18Sort(val label: String) {
    PRICE("가격순"), DISTANCE("가까운 순"), UPDATED("최근 갱신 순")
}

/** The user's approved default/picker order, filtered by available metadata. */
internal fun p18AvailableSorts(hasLocation:Boolean,allowPrice:Boolean):List<P18Sort> =
    P18Sort.entries.filter {
        (it!=P18Sort.PRICE || allowPrice) &&
        (it!=P18Sort.DISTANCE || hasLocation)
    }

internal fun p18DisplayDistance(row:SearchResultDto,location:NearbyCoordinate?):Int? {
    if(location==null || !location.isValid())return null
    val target=NearbyCoordinate(row.latitude,row.longitude)
    return if(target.isValid()) distanceMeters(location,target).roundToInt() else null
}

internal fun p18Sorted(
    rows: List<SearchResultDto>, sort: P18Sort, hasLocation: Boolean,
    at:Instant=Instant.now(),
): List<SearchResultDto> = when(sort) {
    P18Sort.DISTANCE -> if(hasLocation)
        rows.sortedWith(compareBy<SearchResultDto> {it.distanceMeters ?: Int.MAX_VALUE}
            .thenBy {it.barName}) else rows
    P18Sort.PRICE -> rows.sortedWith(compareBy<SearchResultDto> {
        p18Representative(it.options)?.let { option ->
            p18EffectivePrice(option.priceKrw,option.discount,at)
        } ?: Int.MAX_VALUE
    }.thenBy{it.barName})
    P18Sort.UPDATED -> rows.sortedWith(compareByDescending<SearchResultDto> {
        runCatching {Instant.parse(it.menuUpdatedAt)}.getOrNull() ?: Instant.EPOCH
    }.thenBy {it.barName})
}

private val p18Date = DateTimeFormatter.ofPattern("M월 d일")
    .withZone(ZoneId.of("Asia/Seoul"))
internal fun p18MenuUpdated(date: String): String =
    runCatching { p18Date.format(Instant.parse(date)) }.getOrDefault("갱신일 확인 불가")

@Composable
internal fun P18BarRow(
    row: SearchResultDto, showDistance: Boolean, onClick: () -> Unit,
    modifier: Modifier = Modifier,at:Instant=Instant.now(),
) {
    val serving=p18Representative(row.options)
    Row(modifier.fillMaxWidth().heightIn(min=104.dp)
        .clickable(onClick=onClick).padding(vertical=12.dp),
        horizontalArrangement=Arrangement.spacedBy(12.dp),
        verticalAlignment=Alignment.CenterVertically) {
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                Text(row.barName,color=P18Text,fontSize=16.sp,lineHeight=23.sp,
                    fontWeight=FontWeight.SemiBold,
                    modifier=Modifier.weight(1f,false),maxLines=1,
                    overflow=TextOverflow.Ellipsis)
                if(showDistance && row.distanceMeters!=null) {
                    Text(p18Distance(row.distanceMeters),color=P18Muted,fontSize=12.sp)
                }
            }
            Row(verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                if(serving!=null) {
                    Text(p18Price(p18EffectivePrice(serving.priceKrw,serving.discount,at)),
                        color=P18Text,
                        fontWeight=FontWeight.SemiBold,fontSize=16.sp)
                    Text(servingDisplayLabel(serving.pourMl,serving.optionLabel),
                        color=P18Muted,fontSize=13.sp)
                } else Text("가격·용량 정보 없음",color=P18Muted,fontSize=13.sp)
            }
            Text("메뉴 ${p18MenuUpdated(row.menuUpdatedAt)} 기준",
                color=P18Muted,fontSize=12.sp,lineHeight=18.sp)
        }
        if(!row.coverThumbnailUrl.isNullOrBlank())
            P18RemoteBarPhoto(row.coverThumbnailUrl,Modifier.size(64.dp)
                .background(P18Soft,RoundedCornerShape(12.dp)))
        else P18Photo()
    }
}

internal fun p18Distance(distance: Int): String =
    if (distance < 1000) "${distance}m"
    else String.format(java.util.Locale.KOREA,"%.1fkm",distance/1000.0)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
internal fun P18SortPicker(
    sort:P18Sort, hasLocation:Boolean, allowPrice:Boolean,
    onChoose:(P18Sort)->Unit, onClose:()->Unit,
) {
    ModalBottomSheet(onDismissRequest=onClose,
        containerColor=P18Surface,contentColor=P18Text) {
        Column(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,bottom=24.dp),
            verticalArrangement=Arrangement.spacedBy(2.dp)) {
            Text("정렬",color=P18Text,fontSize=20.sp,fontWeight=FontWeight.SemiBold,
                modifier=Modifier.padding(bottom=12.dp))
            p18AvailableSorts(hasLocation,allowPrice).forEach { item ->
                Row(Modifier.fillMaxWidth().height(56.dp)
                    .clickable{onChoose(item)},verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.SpaceBetween) {
                    Text(item.label,color=if(sort==item)P18Gold else P18Text,fontSize=16.sp)
                    if(item==sort) P18SortTick()
                }
            }
            Spacer(Modifier.height(12.dp))
            P18Action("닫기",onClose,modifier=Modifier.fillMaxWidth().height(52.dp))
        }
    }
}

@Composable
internal fun CustomerP18Results(
    initialQuery:String?, initialProductId:String?, source:String,
    onBack:()->Unit, onOpenBar:(String,String?)->Unit,
    onSearchAgain:(String)->Unit = {},
    refreshAfterMissingBar:Boolean=false,
    onMissingBarRefreshConsumed:()->Unit={},
    onMissingProduct:()->Unit={},
    viewModel:P18SearchViewModel=viewModel(),
) {
    val context=LocalContext.current
    val scope=rememberCoroutineScope()
    val userLocation by viewModel.location.collectAsStateWithLifecycle()
    val suggestions by viewModel.suggestions.collectAsStateWithLifecycle()
    val knownTags by viewModel.barTags.collectAsStateWithLifecycle()
    val state by viewModel.state.collectAsStateWithLifecycle()
    // Keep visible discounts and price sorting current at contract boundaries,
    // mirroring the existing 30-second clock in the detail screen.
    var priceClock by remember {mutableStateOf(Instant.now())}
    LaunchedEffect(Unit) {
        while(true) {delay(30_000L);priceClock=Instant.now()}
    }
    val lifecycleOwner = LocalLifecycleOwner.current
    val locationPermissionGranted = ContextCompat.checkSelfPermission(context,
        Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED ||
        ContextCompat.checkSelfPermission(context,
            Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED
    var chooseQuery by rememberSaveable(initialQuery) { mutableStateOf(initialQuery.orEmpty()) }
    var focusRequest by remember { mutableIntStateOf(0) }
    var locationFailed by rememberSaveable { mutableStateOf(false) }
    var exiting by remember { mutableStateOf(false) }
    var locationJob by remember { mutableStateOf<Job?>(null) }
    // An initial ON_RESUME + a permission callback must not run two competing
    // GPS requests whose success/failure arrives in the opposite order.
    fun acquireLocation() {
        if(locationJob?.isActive==true)return
        locationFailed=false
        locationJob=scope.launch {
            try {
                val coordinate=AndroidNearbyLocationSource(context).currentLocation()
                viewModel.setLocation(coordinate)
                locationFailed=false
            } catch(cancelled:CancellationException) {
                throw cancelled
            } catch(_:Exception) {
                locationFailed=true
            }
        }
    }
    // NavHost can enter an already RESUMED lifecycle without an ON_RESUME
    // callback after this composable's observer is registered.
    LaunchedEffect(initialQuery,initialProductId) {
        if(locationPermissionGranted && viewModel.location.value==null)
            acquireLocation()
    }
    DisposableEffect(lifecycleOwner, viewModel, context) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                val allowed = ContextCompat.checkSelfPermission(context,
                    Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED ||
                    ContextCompat.checkSelfPermission(context,
                    Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED
                if (!allowed) viewModel.clearLocation()
                if (allowed && viewModel.location.value == null) acquireLocation()
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    var chosenId by rememberSaveable(initialQuery,initialProductId) {mutableStateOf<String?>(null)}
    var mapMode by rememberSaveable(initialQuery,initialProductId) {mutableStateOf(false)}
    var selectedBarId by rememberSaveable(initialQuery,initialProductId) {mutableStateOf<String?>(null)}
    var mapCamera by remember { mutableStateOf<DiscoveryCamera?>(null) }
    var showSort by remember {mutableStateOf(false)}
    // An explicit sort is sticky; GPS arriving MUST NOT silently override it.
    var selectedSort by rememberSaveable(initialQuery,initialProductId) {
        mutableStateOf<P18Sort?>(null)
    }
    var firstDefaultSort by rememberSaveable(initialQuery,initialProductId) {
        mutableStateOf<P18Sort?>(null)
    }
    fun reload() {
        viewModel.load(if(chosenId==null)initialQuery else null,
            chosenId ?: initialProductId,source,
            location=null,force=true)
    }
    // BAR_NOT_FOUND on the detail destination explicitly invalidates the
    // retained results, but ordinary Back continues to preserve UI state.
    LaunchedEffect(refreshAfterMissingBar) {
        if(refreshAfterMissingBar) {
            onMissingBarRefreshConsumed()
            reload()
        }
    }
    val locationLauncher=rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if(grants.values.any{it}) acquireLocation()
    }
    fun requestLocation() {
        val granted=ContextCompat.checkSelfPermission(context,
            Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context,
                Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED
        if(granted) acquireLocation()
        else locationLauncher.launch(arrayOf(
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.ACCESS_FINE_LOCATION))
    }
    // Search once per QUERY/PRODUCT selection, not once per GPS update.
    // Newly obtained GPS drives a local haversine distance for rendered bars.
    // This prevents a second Loading state, sort flip and stale 03-e1.
    LaunchedEffect(initialQuery,initialProductId,chosenId,source) {
        viewModel.load(if(chosenId==null)initialQuery else null,
            chosenId ?: initialProductId,
            source,location=null)
    }
    val ready=(state as? P18SearchState.Ready)?.response
    val original=p18OriginalResponse(initialQuery,initialProductId,suggestions,ready)
    val choices=original?.matchedProducts.orEmpty()
    val canSkip=initialProductId!=null || (original!=null &&
        original.matchType=="alias_exact" && choices.size==1)
    val choose=chosenId==null && !canSkip && choices.isNotEmpty() &&
        (choices.size>1 || original?.matchType!="alias_exact")
    val result=p18ResolvedResult(chosenId,initialProductId,canSkip,original,ready)
    val allowsPrice=result?.items?.any{it.options.isNotEmpty()}==true
    val availableSorts=p18AvailableSorts(userLocation!=null,allowsPrice)
    val sort=selectedSort?.takeIf{it in availableSorts}
        ?:firstDefaultSort?.takeIf{it in availableSorts}
        ?:availableSorts.first()
    LaunchedEffect(result,availableSorts) {
        if(result!=null && firstDefaultSort==null)firstDefaultSort=availableSorts.first()
    }
    fun navigateBack() {
        if (chosenId != null) {
            chosenId = null
            mapMode = false
            selectedBarId = null
            exiting = false
        } else if (!exiting) {
            exiting = true
            onBack()
        }
    }
    BackHandler(enabled=true) { navigateBack() }
    if(showSort) P18SortPicker(sort,userLocation!=null,allowPrice=allowsPrice,
        onChoose={selectedSort=it;showSort=false},onClose={showSort=false})
    Column(Modifier.fillMaxSize().background(P18Bg).testTag("customer-results")) {
        when {
            state is P18SearchState.Loading &&
                (original==null || chosenId!=null || initialProductId!=null) -> {
                P18LoadingScene("위스키 찾는 중",::navigateBack,Modifier.weight(1f))
            }
            state is P18SearchState.Error -> {
                P18SearchTopBar(::navigateBack, chooseQuery)
                P18FailureBody("검색하지 못했어요",
                    "연결을 확인하고 다시 시도해 주세요.","다시 시도",
                    BmIconId.ERROR,::reload,primary=true,modifier=Modifier.weight(1f),topInset=120)
            }
            (chosenId!=null || initialProductId!=null) &&
                state is P18SearchState.Ready && ready?.matchType=="none" -> {
                LaunchedEffect(ready) { onMissingProduct() }
                P18SearchTopBar(::navigateBack,chooseQuery)
                P18FailureBody("상품 정보를 찾을 수 없어요",
                    "현재 등록된 상품이 아닙니다.\\n다른 위스키를 선택해 주세요.",
                    "다른 위스키 보기",icon=BmIconId.EMPTY,
                    onAction=::navigateBack,modifier=Modifier.weight(1f))
            }
            state is P18SearchState.InvalidQuery ||
                (chosenId==null && initialProductId==null &&
                    original!=null && original.matchedProducts.isEmpty()) -> {
                P18SearchTopBar(::navigateBack,chooseQuery,{chooseQuery=it},
                    {if(chooseQuery.isNotBlank())onSearchAgain(chooseQuery)},
                    editable=true,focusRequestToken=focusRequest)
                P18FailureBody("어떤 위스키인지\n알아보지 못했어요",
                    "영어 이름이나 다른 표기로\n다시 찾아보세요.",
                    "검색어 고치기",icon=BmIconId.SEARCH,
                    onAction={chooseQuery="";focusRequest++},
                    modifier=Modifier.weight(1f))
            }
            choose -> {
                Row(Modifier.fillMaxWidth().heightIn(min=72.dp)
                    .padding(start=8.dp,end=20.dp),
                    verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(4.dp)) {
                    P18Back(::navigateBack)
                    Box(Modifier.weight(1f)){
                        P18SearchField(chooseQuery,{chooseQuery=it},
                            {if(chooseQuery.isNotBlank())onSearchAgain(chooseQuery)},
                            modifier=Modifier.fillMaxWidth())
                    }
                }
                Text("어떤 ${initialQuery.orEmpty()}인가요?",
                    modifier=Modifier.padding(start=20.dp,end=20.dp,top=8.dp,bottom=12.dp),
                    style=MaterialTheme.typography.headlineSmall,
                    fontSize=24.sp,lineHeight=32.sp,color=P18Text)
                LazyColumn(Modifier.fillMaxSize().padding(horizontal=20.dp)) {
                    items(choices,key={it.productId}) { product ->
                        Row(Modifier.fillMaxWidth().heightIn(min=72.dp)
                            .clickable { chosenId=product.productId;mapMode=false }
                            .testTag("customer-choice-${product.productId}"),
                            verticalAlignment=Alignment.CenterVertically,
                            horizontalArrangement=Arrangement.spacedBy(14.dp)) {
                            P18Bottle(product.displayName,24.dp,38.dp)
                            Text(product.displayName,Modifier.weight(1f),fontSize=16.sp,
                                fontWeight=FontWeight.SemiBold,color=P18Text)
                            Text(if(product.resultCount==0)"파는 매장 없음"
                                else "매장 ${product.resultCount}곳",
                                color=P18Muted,fontSize=13.sp)
                            Text("›",color=P18Muted,fontSize=20.sp)
                        }
                        Box(Modifier.fillMaxWidth().height(1.dp).background(P18Line))
                    }
                }
            }
            chosenId!=null && state is P18SearchState.Loading -> {
                P18LoadingScene("위스키 찾는 중",::navigateBack,Modifier.weight(1f))
            }
            result!=null && result.items.isEmpty() -> {
                P18SearchTopBar(::navigateBack,chooseQuery)
                val productName = result.matchedProducts.firstOrNull()?.displayName
                    ?: choices.firstOrNull{it.productId==chosenId}?.displayName.orEmpty()
                P18FailureBody("아직 파는 매장이 없어요",
                    "등록된 매장 메뉴판에서\n이 위스키를 찾지 못했어요.",
                    if(initialQuery!=null)"다른 ${initialQuery} 보기" else "다른 위스키 보기",
                    icon=BmIconId.EMPTY,onAction=::navigateBack,
                    modifier=Modifier.weight(1f),productName=productName,topInset=96)
            }
            result!=null -> {
                val selectedProductId = chosenId ?: initialProductId
                val product=result.matchedProducts.firstOrNull { it.productId == selectedProductId }
                    ?: choices.firstOrNull { it.productId == selectedProductId }
                    ?: result.matchedProducts.firstOrNull() ?: choices.firstOrNull()
                // API only includes distance when lat/lng were sent. Use the
                // same haversine formula on published coordinates if GPS arrives
                // later, without redoing the entire search or changing the sort.
                val distanceRows=result.items.map{row->
                    row.copy(distanceMeters=p18DisplayDistance(row,userLocation))
                }
                val items=p18Sorted(distanceRows,sort,userLocation!=null,priceClock)
                if(mapMode) {
                    val focusedBarId=selectedBarId ?: items.firstOrNull()?.barId
                    LaunchedEffect(focusedBarId) {
                        if(focusedBarId!=null)viewModel.loadBarTags(focusedBarId)
                    }
                    P18ResultsMap(result,items,product?.displayName.orEmpty(),
                        ::navigateBack, {mapMode=false},selectedBarId,userLocation,
                        knownTags[focusedBarId].orEmpty(),mapCamera,{mapCamera=it},
                        onSelect={id->if(selectedBarId==id)onOpenBar(id,product?.productId)
                            else selectedBarId=id},
                        onOpenBar={onOpenBar(it,product?.productId)},at=priceClock)
                } else {
                    Row(Modifier.fillMaxWidth().height(72.dp)
                        .padding(start=8.dp,end=12.dp),verticalAlignment=Alignment.CenterVertically){
                        P18Back(::navigateBack)
                        Text(if(initialProductId!=null)"" else "‘${initialQuery.orEmpty()}’ 검색",
                            color=P18Muted,fontSize=14.sp)
                    }
                    Row(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,top=4.dp),
                        horizontalArrangement=Arrangement.spacedBy(12.dp),
                        verticalAlignment=Alignment.CenterVertically) {
                        P18Bottle(product?.displayName.orEmpty())
                        Column {
                            Text(product?.displayName.orEmpty(),color=P18Gold,
                                fontWeight=FontWeight.SemiBold,fontSize=14.sp)
                            Text("파는 매장 ${items.size}곳",color=P18Text,
                                style=MaterialTheme.typography.headlineSmall,fontSize=24.sp)
                        }
                    }
                    if(userLocation==null &&
                        (!locationPermissionGranted || locationFailed)) {
                        P18LocationBanner(::requestLocation,
                            Modifier.padding(horizontal=20.dp,vertical=10.dp),
                            locationFailed=locationFailed)
                    }
                    Row(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,top=12.dp,bottom=4.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.SpaceBetween) {
                        P18SortTrigger(sort.label,{showSort=true})
                        P18ModeButton("지도",{mapMode=true})
                    }
                    LazyColumn(Modifier.fillMaxSize().padding(horizontal=20.dp)) {
                        items(items,key={it.barId+it.productId}) {row->
                            P18BarRow(row,userLocation!=null,
                                onClick={onOpenBar(row.barId,product?.productId)},
                                at=priceClock)
                            Box(Modifier.fillMaxWidth().height(1.dp).background(P18Line))
                        }
                    }
                }
            }
            else -> {
                P18LoadingScene("위스키 찾는 중",::navigateBack,Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun P18ResultsMap(
    response:SearchBarsResponseDto, items:List<SearchResultDto>,name:String,
    onBack:()->Unit,onList:()->Unit,selected:String?,userLocation:NearbyCoordinate?,
    selectedTags:List<String>,initialCamera:DiscoveryCamera?,onCamera:(DiscoveryCamera)->Unit,
    onSelect:(String)->Unit,onOpenBar:(String)->Unit,at:Instant,
) {
    val selectedItem=items.firstOrNull{it.barId==selected} ?: items.firstOrNull()
    val pins=items.mapNotNull { item ->
        val center=NearbyCoordinate(item.latitude,item.longitude)
        if(!center.isValid()) null else MapBar(item.barId,item.barName,item.address,
            center,item.menuUpdatedAt)
    }
    val center=pins.firstOrNull()?.location
    var mapView by remember {mutableStateOf<com.kakao.vectormap.MapView?>(null)}
    Box(Modifier.fillMaxSize().testTag("customer-results-map")) {
        if(center!=null) NearbyKakaoMap(
            origin=center, bars=pins,selectedBarId=selectedItem?.barId,
            focusTarget=pins.firstOrNull{it.barId==selectedItem?.barId},
            focusBarId=null,initialCamera=initialCamera,listCovered=false,
            searchedPlace=null,focusSearchedPlace=null,
            onSearchedPlaceFocusApplied={},onFocusApplied={},
            onCameraChanged={center,zoom->onCamera(DiscoveryCamera(center,zoom))},
            onMapCameraMoving={},
            onMapViewportUnavailable={},viewportRetryToken=0,
            onSelectBar=onSelect,onViewportChanged={},recenterToken=0,
            onMapViewChanged={mapView=it},modifier=Modifier.fillMaxSize(),
            p18Markers=true,showOriginMarker=userLocation!=null,
            markerDataRevision=at.epochSecond/30L,
            userLocation=userLocation,
            p18MarkerSubtitle={id->
                items.firstOrNull{it.barId==id}?.let{row->
                    p18Representative(row.options)?.let{ option->
                        p18Price(p18EffectivePrice(option.priceKrw,option.discount,at))+" · "+
                            (servingDisplayLabel(option.pourMl,option.optionLabel))
                    }
                }
            })
        else Box(Modifier.fillMaxSize().background(P18Surface),
            contentAlignment=Alignment.Center) {
            Text("지도의 매장 위치를 불러오지 못했어요",color=P18Text)
        }
        Row(Modifier.fillMaxWidth().padding(start=8.dp,end=12.dp,top=12.dp),
            verticalAlignment=Alignment.CenterVertically,
            horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            P18Back(onBack,dark=true)
            Row(Modifier.weight(1f).height(48.dp)
                .background(P18Bg,RoundedCornerShape(12.dp))
                .padding(horizontal=12.dp),
                verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                P18Bottle(name,16.dp,26.dp)
                Text(name,Modifier.weight(1f),color=P18Text,
                    fontSize=15.sp,maxLines=1,overflow=TextOverflow.Ellipsis)
                Text("${items.size}곳",color=P18Muted,fontSize=13.sp)
            }
            P18ModeButton("목록",onList,dark=true)
        }
        if(selectedItem!=null) {
            Column(Modifier.align(Alignment.BottomCenter).fillMaxWidth()
                .background(P18Bg,RoundedCornerShape(topStart=24.dp,topEnd=24.dp))
                .clickable { onOpenBar(selectedItem.barId) }
                .padding(start=20.dp,end=20.dp,top=10.dp,bottom=10.dp),
                horizontalAlignment=Alignment.CenterHorizontally) {
                Box(Modifier.width(36.dp).height(4.dp)
                    .background(BottleMapPalette.outline,RoundedCornerShape(4.dp)))
                Row(Modifier.fillMaxWidth().padding(top=8.dp,bottom=2.dp),
                    verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                    Column(Modifier.weight(1f),
                        verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Row(verticalAlignment=Alignment.CenterVertically,
                            horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                            Text(selectedItem.barName,Modifier.weight(1f,false),
                                color=P18Text,fontSize=16.sp,fontWeight=FontWeight.SemiBold,
                                maxLines=1,overflow=TextOverflow.Ellipsis)
                            if(userLocation!=null && selectedItem.distanceMeters!=null)
                                Text(p18Distance(selectedItem.distanceMeters),
                                    color=P18Muted,fontSize=12.sp)
                        }
                        if(selectedTags.isNotEmpty()) Row(
                            horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                            selectedTags.take(2).forEach { tag ->
                                Box(Modifier.background(P18Elevated,RoundedCornerShape(50))
                                    .border(1.dp,P18Line,RoundedCornerShape(50))
                                    .padding(horizontal=8.dp,vertical=2.dp)) {
                                    Text(tag,color=P18Text,fontSize=11.sp)
                                }
                            }
                        }
                        val serving=p18Representative(selectedItem.options)
                        if(serving!=null) Row(
                            horizontalArrangement=Arrangement.spacedBy(6.dp),
                            verticalAlignment=Alignment.CenterVertically) {
                            Text(p18Price(p18EffectivePrice(serving.priceKrw,serving.discount,at)),
                                color=P18Text,fontSize=16.sp,fontWeight=FontWeight.SemiBold)
                            Text(servingDisplayLabel(serving.pourMl,serving.optionLabel),
                                color=P18Muted,fontSize=13.sp)
                        }
                        Text("메뉴 ${p18MenuUpdated(selectedItem.menuUpdatedAt)} 기준",
                            color=P18Muted,fontSize=12.sp)
                    }
                    if(!selectedItem.coverThumbnailUrl.isNullOrBlank())
                        P18RemoteBarPhoto(selectedItem.coverThumbnailUrl,
                            Modifier.size(72.dp))
                    else P18Photo(size=72.dp)
                }
            }
        }
    }
}

@Composable
private fun P18SearchTopBar(
    onBack:()->Unit, query:String="", onQuery:(String)->Unit={}, onSubmit:()->Unit={},
    editable:Boolean=false, focusRequestToken:Int=0,
) {
    Row(Modifier.fillMaxWidth().heightIn(min=72.dp)
        .padding(start=8.dp,end=20.dp,top=8.dp,bottom=8.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(4.dp)) {
        P18Back(onBack)
        if(query.isNotEmpty() || editable) {
            P18SearchField(query,onQuery,onSubmit,
                modifier=Modifier.weight(1f),focusRequestToken=focusRequestToken)
        }
    }
}
