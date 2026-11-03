
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
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.network.ApiClient
import com.zerotoone.bottlemap.network.BottleMapApiException
import com.zerotoone.bottlemap.network.MatchedProductDto
import com.zerotoone.bottlemap.network.SearchBarsResponseDto
import com.zerotoone.bottlemap.network.SearchResultDto
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import com.zerotoone.bottlemap.ui.common.BmIconId
import com.zerotoone.bottlemap.ui.common.GlassFillLoading
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter

internal sealed interface P18SearchState {
    data object Loading : P18SearchState
    data class Ready(val response: SearchBarsResponseDto) : P18SearchState
    data class Error(val message: String) : P18SearchState
}

internal class P18SearchViewModel : ViewModel() {
    private val mutable = MutableStateFlow<P18SearchState>(P18SearchState.Loading)
    val state = mutable.asStateFlow()
    private var job: Job? = null
    private var version = 0L
    private var lastKey: String? = null
    // Keep the full brand candidate list independently of selected-product responses.
    private val _suggestions = MutableStateFlow<SearchBarsResponseDto?>(null)
    val suggestions = _suggestions.asStateFlow()
    // The result destination's ViewModel survives a detail push/pop.
    private val _location = MutableStateFlow<NearbyCoordinate?>(null)
    val location = _location.asStateFlow()
    fun setLocation(value: NearbyCoordinate) { if (value.isValid()) _location.value = value }
    fun clearLocation() { _location.value = null }
    fun load(query: String?, productId: String?, source: String,
             location: NearbyCoordinate? = null, force: Boolean = false) {
        val key = listOf(query, productId, source, location?.latitude, location?.longitude).joinToString("|")
        if (!force && key == lastKey) return
        lastKey=key
        job?.cancel()
        val request = ++version
        mutable.value = P18SearchState.Loading
        job=viewModelScope.launch {
            try {
                val result=ApiClient.call {
                    ApiClient.api.searchProductP18(
                        query=query?.takeIf {it.isNotBlank()},
                        productId=productId?.takeIf {it.isNotBlank()},
                        latitude=location?.latitude, longitude=location?.longitude,
                        source=source)
                }
                if (request==version) {
                    if (query != null && productId == null && result.matchedProducts.isNotEmpty()) {
                        _suggestions.value = result
                    }
                    mutable.value=P18SearchState.Ready(result)
                }
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (error: Exception) {
                if (request==version) {
                    val msg=if(error is BottleMapApiException &&
                        error.code=="NETWORK_ERROR") "연결을 확인하고 다시 시도해 주세요."
                        else "연결을 확인하고 다시 시도해 주세요."
                    mutable.value=P18SearchState.Error(msg)
                }
            }
        }
    }
    fun retry() { lastKey=null }
}

internal enum class P18Sort(val label: String) {
    DISTANCE("가까운 순"), PRICE("가격순"), UPDATED("최근 갱신 순")
}

internal fun p18Sorted(
    rows: List<SearchResultDto>, sort: P18Sort, hasLocation: Boolean
): List<SearchResultDto> = when(sort) {
    P18Sort.DISTANCE -> if(hasLocation)
        rows.sortedWith(compareBy<SearchResultDto> {it.distanceMeters ?: Int.MAX_VALUE}
            .thenBy {it.barName}) else rows
    P18Sort.PRICE -> rows.sortedWith(compareBy<SearchResultDto> {
        p18Representative(it.options)?.let { option ->
            p18EffectivePrice(option.priceKrw,option.discount)
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
    modifier: Modifier = Modifier,
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
                    Text(p18Price(p18EffectivePrice(serving.priceKrw,serving.discount)),
                        color=P18Text,
                        fontWeight=FontWeight.SemiBold,fontSize=16.sp)
                    Text(serving.pourMl?.let{"${it}ml"} ?: serving.optionLabel.orEmpty(),
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
            P18Sort.entries.filter {(it!=P18Sort.DISTANCE || hasLocation) &&
                (it!=P18Sort.PRICE || allowPrice) }.forEach { item ->
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
    viewModel:P18SearchViewModel=viewModel(),
) {
    val context=LocalContext.current
    val scope=rememberCoroutineScope()
    val userLocation by viewModel.location.collectAsStateWithLifecycle()
    val suggestions by viewModel.suggestions.collectAsStateWithLifecycle()
    val state by viewModel.state.collectAsStateWithLifecycle()
    val lifecycleOwner = LocalLifecycleOwner.current
    var chooseQuery by rememberSaveable(initialQuery) { mutableStateOf(initialQuery.orEmpty()) }
    var focusRequest by remember { mutableIntStateOf(0) }
    var locationFailed by rememberSaveable { mutableStateOf(false) }
    var exiting by remember { mutableStateOf(false) }
    DisposableEffect(lifecycleOwner, viewModel, context) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) {
                val allowed = ContextCompat.checkSelfPermission(context,
                    Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED ||
                    ContextCompat.checkSelfPermission(context,
                    Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED
                if (!allowed) viewModel.clearLocation()
                if (allowed && viewModel.location.value == null) scope.launch {
                    runCatching { AndroidNearbyLocationSource(context).currentLocation() }
                        .onSuccess { viewModel.setLocation(it);locationFailed=false }
                        .onFailure { locationFailed=true }
                }
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    var initialResponse by remember(initialQuery,initialProductId) {
        mutableStateOf<SearchBarsResponseDto?>(null)
    }
    var chosenId by rememberSaveable(initialQuery,initialProductId) {mutableStateOf<String?>(null)}
    var mapMode by rememberSaveable(initialQuery,initialProductId) {mutableStateOf(false)}
    var selectedBarId by rememberSaveable(initialQuery,initialProductId) {mutableStateOf<String?>(null)}
    var mapCamera by remember { mutableStateOf<DiscoveryCamera?>(null) }
    var showSort by remember {mutableStateOf(false)}
    var sort by rememberSaveable {mutableStateOf(P18Sort.UPDATED)}
    LaunchedEffect(userLocation) { if(userLocation!=null)sort=P18Sort.DISTANCE }
    fun reload() {
        viewModel.load(if(chosenId==null)initialQuery else null,
            chosenId ?: initialProductId, if(chosenId==null)source else "input",
            userLocation,force=true)
    }
    val locationLauncher=rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()) { grants ->
        if(grants.values.any{it}) {
            scope.launch {
                runCatching {AndroidNearbyLocationSource(context).currentLocation()}
                    .onSuccess { viewModel.setLocation(it);locationFailed=false }
                    .onFailure { locationFailed=true }
            }
        }
    }
    fun requestLocation() {
        val granted=ContextCompat.checkSelfPermission(context,
            Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context,
                Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED
        if(granted) scope.launch {
            runCatching {AndroidNearbyLocationSource(context).currentLocation()}
                .onSuccess { viewModel.setLocation(it);locationFailed=false }
                .onFailure { locationFailed=true }
        } else locationLauncher.launch(arrayOf(
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.ACCESS_FINE_LOCATION))
    }
    LaunchedEffect(initialQuery,initialProductId,chosenId,userLocation) {
        viewModel.load(if(chosenId==null) initialQuery else null,
            chosenId ?: initialProductId,
            if(chosenId==null)source else "input",userLocation)
    }
    val ready=(state as? P18SearchState.Ready)?.response
    if(ready!=null && chosenId==null && initialResponse==null) initialResponse=ready
    val original=suggestions ?: initialResponse ?: ready
    val choices=original?.matchedProducts.orEmpty()
    val canSkip=initialProductId!=null || (original!=null &&
        original.matchType=="alias_exact" && choices.size==1)
    val choose=chosenId==null && !canSkip && choices.isNotEmpty() &&
        (choices.size>1 || original?.matchType!="alias_exact")
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
    if(showSort) P18SortPicker(sort,userLocation!=null,allowPrice=true,
        onChoose={sort=it;showSort=false},onClose={showSort=false})
    Column(Modifier.fillMaxSize().background(P18Bg).testTag("customer-results")) {
        when {
            state is P18SearchState.Loading && original==null -> {
                P18SearchTopBar(::navigateBack,initialQuery.orEmpty())
                P18LoadingBody("‘${initialQuery ?: "위스키"}’ 찾는 중",Modifier.weight(1f))
            }
            state is P18SearchState.Error -> {
                P18SearchTopBar(::navigateBack, chooseQuery)
                P18FailureBody("검색하지 못했어요",
                    "연결을 확인하고 다시 시도해 주세요.","다시 시도",
                    BmIconId.ERROR,::reload,primary=true,modifier=Modifier.weight(1f),topInset=120)
            }
            original!=null && original.matchedProducts.isEmpty() -> {
                P18SearchTopBar(::navigateBack,chooseQuery,{chooseQuery=it},
                    {if(chooseQuery.isNotBlank())onSearchAgain(chooseQuery)},
                    editable=true,focusRequestToken=focusRequest)
                P18FailureBody("어떤 위스키인지\n알아보지 못했어요",
                    "영어 이름이나 다른 표기로\n다시 찾아보세요.",
                    "검색어 고치기",icon=BmIconId.SEARCH,onAction={focusRequest++},
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
                P18SearchTopBar(::navigateBack,chooseQuery)
                P18LoadingBody("위스키 찾는 중",Modifier.weight(1f))
            }
            ready!=null && ready.items.isEmpty() -> {
                P18SearchTopBar(::navigateBack,chooseQuery)
                val productName = ready.matchedProducts.firstOrNull()?.displayName
                    ?: choices.firstOrNull{it.productId==chosenId}?.displayName.orEmpty()
                P18FailureBody("아직 파는 매장이 없어요",
                    "등록된 매장 메뉴판에서\n이 위스키를 찾지 못했어요.",
                    if(initialQuery!=null)"다른 ${initialQuery} 보기" else "다른 위스키 보기",
                    icon=BmIconId.EMPTY,onAction=::navigateBack,
                    modifier=Modifier.weight(1f),productName=productName,topInset=96)
            }
            ready!=null -> {
                val selectedProductId = chosenId ?: initialProductId
                val product=ready.matchedProducts.firstOrNull { it.productId == selectedProductId }
                    ?: choices.firstOrNull { it.productId == selectedProductId }
                    ?: ready.matchedProducts.firstOrNull() ?: choices.firstOrNull()
                val items=p18Sorted(ready.items,sort,userLocation!=null)
                if(mapMode) {
                    P18ResultsMap(ready,items,product?.displayName.orEmpty(),
                        ::navigateBack, {mapMode=false},selectedBarId,userLocation!=null,
                        mapCamera,{mapCamera=it},
                        onSelect={id->if(selectedBarId==id)onOpenBar(id,product?.productId)
                            else selectedBarId=id},
                        onOpenBar={onOpenBar(it,product?.productId)})
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
                    if(userLocation==null) {
                        P18LocationBanner(::requestLocation,
                            Modifier.padding(horizontal=20.dp,vertical=10.dp),
                            locationFailed=locationFailed)
                    }
                    Row(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,top=12.dp,bottom=4.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.SpaceBetween) {
                        P18SortTrigger((if(userLocation==null && sort==P18Sort.DISTANCE)
                            P18Sort.UPDATED else sort).label,{showSort=true})
                        P18ModeButton("지도",{mapMode=true})
                    }
                    LazyColumn(Modifier.fillMaxSize().padding(horizontal=20.dp)) {
                        items(items,key={it.barId+it.productId}) {row->
                            P18BarRow(row,userLocation!=null,
                                onClick={onOpenBar(row.barId,product?.productId)})
                            Box(Modifier.fillMaxWidth().height(1.dp).background(P18Line))
                        }
                    }
                }
            }
            else -> {
                P18SearchTopBar(::navigateBack,chooseQuery)
                P18LoadingBody("위스키 찾는 중",Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun P18ResultsMap(
    response:SearchBarsResponseDto, items:List<SearchResultDto>,name:String,
    onBack:()->Unit,onList:()->Unit,selected:String?,hasLocation:Boolean,
    initialCamera:DiscoveryCamera?,onCamera:(DiscoveryCamera)->Unit,
    onSelect:(String)->Unit,onOpenBar:(String)->Unit,
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
            p18Markers=true,showOriginMarker=false,
            p18MarkerSubtitle={id->
                items.firstOrNull{it.barId==id}?.let{row->
                    p18Representative(row.options)?.let{ option->
                        p18Price(p18EffectivePrice(option.priceKrw,option.discount))+" · "+
                            (option.pourMl?.let{"${it}ml"}?:option.optionLabel.orEmpty())
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
                .padding(start=20.dp,end=20.dp,top=10.dp,bottom=24.dp),
                horizontalAlignment=Alignment.CenterHorizontally) {
                Box(Modifier.width(36.dp).height(4.dp)
                    .background(BottleMapPalette.outline,RoundedCornerShape(4.dp)))
                P18BarRow(selectedItem,hasLocation,{onOpenBar(selectedItem.barId)})
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
