
package com.zerotoone.bottlemap.ui.customer

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.Settings
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import androidx.lifecycle.viewModelScope
import com.zerotoone.bottlemap.data.AndroidNearbyLocationSource
import com.zerotoone.bottlemap.data.BackendMapBarsRepository
import com.zerotoone.bottlemap.data.MapBar
import com.zerotoone.bottlemap.data.MapBounds
import com.zerotoone.bottlemap.data.MapPlace
import com.zerotoone.bottlemap.data.NearbyCoordinate
import com.zerotoone.bottlemap.data.distanceMeters
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.common.BmIconId
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

/** The Kakao map's initial center is a public area, never an invented user location. */
internal val P18DefaultMapCenter=NearbyCoordinate(37.478321,126.951234)

internal sealed interface P18ExploreState {
    data object Initial:P18ExploreState
    data object Loading:P18ExploreState
    data object TooWide:P18ExploreState
    data class Ready(val bars:List<MapBar>):P18ExploreState
    data object Error:P18ExploreState
}

internal class P18ExploreViewModel(
    private val source: com.zerotoone.bottlemap.data.MapBarsSource=BackendMapBarsRepository()
):ViewModel() {
    private val mutable=MutableStateFlow<P18ExploreState>(P18ExploreState.Initial)
    val state=mutable.asStateFlow()
    private var job:Job?=null
    private var lastBounds:MapBounds?=null
    private var seq=0L
    fun load(viewport:MapViewport,force:Boolean=false) {
        val bounds=viewport.bounds
        if(!bounds.isSupportedByBackend()) {
            job?.cancel();++seq;lastBounds=bounds
            mutable.value=P18ExploreState.TooWide;return
        }
        if(!force && bounds.isNearlySameAs(lastBounds?:bounds) &&
            mutable.value is P18ExploreState.Ready)return
        lastBounds=bounds
        val v=++seq
        job?.cancel()
        mutable.value=P18ExploreState.Loading
        job=viewModelScope.launch {
            delay(350)
            try {
                val result=source.listMapBars(bounds)
                if(v==seq)mutable.value=P18ExploreState.Ready(result.distinctBy{it.barId})
            }catch(cancelled:CancellationException){throw cancelled}
            catch(_:Exception){if(v==seq)mutable.value=P18ExploreState.Error}
        }
    }
    fun moving() {if(mutable.value !is P18ExploreState.Initial) {
        job?.cancel();++seq;mutable.value=P18ExploreState.Loading
    }}
    fun unavailable() {job?.cancel();++seq;mutable.value=P18ExploreState.Error}
    fun retry() {lastBounds?.let{load(MapViewport(it),true)}}
    // Both location and camera survive a Bar Detail push/pop.
    private val _location=MutableStateFlow<NearbyCoordinate?>(null)
    val location=_location.asStateFlow()
    fun setLocation(point:NearbyCoordinate) { if(point.isValid()) _location.value=point }
    var camera:DiscoveryCamera? = null
        private set
    fun rememberCamera(center:NearbyCoordinate,zoom:Int) {
        if(center.isValid()&&zoom in 1..21)camera=DiscoveryCamera(center,zoom)
    }
}

private fun p18BrowseOrdered(bars:List<MapBar>,sort:P18Sort,origin:NearbyCoordinate?)
    :List<MapBar> = when {
    sort==P18Sort.DISTANCE && origin!=null ->
        bars.sortedBy{distanceMeters(origin,it.location)}
    else -> bars.sortedWith(compareByDescending<MapBar>{
        runCatching{java.time.Instant.parse(it.menuUpdatedAt)}.getOrNull()
            ?:java.time.Instant.EPOCH
    }.thenBy{it.name})
}

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
internal fun CustomerP18Explore(
    onBack:()->Unit,onOpenBar:(String)->Unit,
    viewModel:P18ExploreViewModel=viewModel(),
    searchViewModel:MapPlaceSearchViewModel=mapPlaceSearchViewModel(),
) {
    val context=LocalContext.current
    val scope=rememberCoroutineScope()
    val state by viewModel.state.collectAsStateWithLifecycle()
    val placeState by searchViewModel.state.collectAsStateWithLifecycle()
    val selectedPlace by searchViewModel.selected.collectAsStateWithLifecycle()
    val focusPlace by searchViewModel.focus.collectAsStateWithLifecycle()
    var listVisible by rememberSaveable {mutableStateOf(false)}
    var searchVisible by rememberSaveable {mutableStateOf(false)}
    var searchText by rememberSaveable {mutableStateOf("")}
    var selectedId by rememberSaveable {mutableStateOf<String?>(null)}
    var showSort by remember {mutableStateOf(false)}
    var sort by rememberSaveable {mutableStateOf(P18Sort.UPDATED)}
    val location by viewModel.location.collectAsStateWithLifecycle()
    var locationDenied by remember {mutableStateOf(false)}
    var recenterToken by remember {mutableIntStateOf(0)}
    var goToGwanak by remember {mutableStateOf(false)}
    var errorLocation by remember {mutableStateOf(false)}
    var mapView by remember {mutableStateOf<com.kakao.vectormap.MapView?>(null)}
    val bars=(state as? P18ExploreState.Ready)?.bars.orEmpty()
    val ordered=p18BrowseOrdered(bars,sort,location)
    val chosen=bars.firstOrNull{it.barId==selectedId}
    val launcher=rememberLauncherForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()) { permissions ->
        if(permissions.values.any{it})scope.launch {
            runCatching{AndroidNearbyLocationSource(context).currentLocation()}
                .onSuccess{viewModel.setLocation(it);goToGwanak=false;recenterToken++}
                .onFailure{errorLocation=true}
        } else locationDenied=true
    }
    fun requestCurrentLocation() {
        val fine=ContextCompat.checkSelfPermission(context,
            Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED
        val coarse=ContextCompat.checkSelfPermission(context,
            Manifest.permission.ACCESS_COARSE_LOCATION)==PackageManager.PERMISSION_GRANTED
        if(fine||coarse)scope.launch {
            runCatching{AndroidNearbyLocationSource(context).currentLocation()}
                .onSuccess{location=it;recenterToken++}
                .onFailure{errorLocation=true}
        } else launcher.launch(arrayOf(
            Manifest.permission.ACCESS_COARSE_LOCATION,
            Manifest.permission.ACCESS_FINE_LOCATION))
    }
    LaunchedEffect(location) {if(location!=null)sort=P18Sort.DISTANCE}
    if(showSort) P18SortPicker(sort,location!=null,allowPrice=false,
        onChoose={sort=it;showSort=false},onClose={showSort=false})
    if(locationDenied || errorLocation) ModalBottomSheet(
        onDismissRequest={locationDenied=false;errorLocation=false},
        containerColor=P18Surface,contentColor=P18Text) {
        Column(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,bottom=24.dp),
            verticalArrangement=Arrangement.spacedBy(16.dp)) {
            Text(if(errorLocation)"위치 서비스가 꺼져 있어요" else "위치 권한이 꺼져 있어요",
                fontSize=20.sp,lineHeight=28.sp,fontWeight=FontWeight.SemiBold,color=P18Text)
            Text(if(errorLocation)
                "위치 설정을 확인하면 가까운 매장과 거리를 볼 수 있어요. 위치 없이도 지도를 움직여 찾을 수 있어요."
                else "설정에서 위치를 허용하면 가까운 매장과 거리를 볼 수 있어요. 위치 없이도 지도를 움직여 찾을 수 있어요.",
                fontSize=14.sp,lineHeight=21.sp,color=P18Muted)
            P18Action(if(errorLocation)"위치 설정 열기" else "설정 열기",{
                context.startActivity(if(errorLocation)
                    Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS) else
                    Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).apply {
                        if(!errorLocation)data=Uri.parse("package:"+context.packageName)
                    })
                locationDenied=false;errorLocation=false
            },primary=true,modifier=Modifier.fillMaxWidth().height(56.dp))
            Box(Modifier.fillMaxWidth().height(48.dp).clickable {
                locationDenied=false;errorLocation=false
            },contentAlignment=Alignment.Center) {
                Text("위치 없이 둘러보기",color=P18Muted,fontSize=14.sp,
                    fontWeight=FontWeight.Medium)
            }
        }
    }
    fun back() {
        when {
            searchVisible -> {searchVisible=false;searchViewModel.dismissResults()}
            else->onBack()
        }
    }
    BackHandler {back()}
    LaunchedEffect(listVisible,searchVisible,mapView) {
        mapView?.let{if(listVisible||searchVisible)hideNearbyNativeSurface(it)
            else showNearbyNativeSurface(it)}
    }
    Box(Modifier.fillMaxSize().background(P18Bg).testTag("customer-map-explore")) {
        NearbyKakaoMap(origin=if(goToGwanak)P18DefaultMapCenter else
            location?:P18DefaultMapCenter,
            bars=bars,selectedBarId=selectedId,
            focusTarget=chosen,focusBarId=null,initialCamera=viewModel.camera,
            listCovered=listVisible||searchVisible,
            searchedPlace=selectedPlace,focusSearchedPlace=focusPlace,
            onSearchedPlaceFocusApplied=searchViewModel::consumeFocus,
            onFocusApplied={},onCameraChanged=viewModel::rememberCamera,
            onMapCameraMoving=viewModel::moving,
            onMapViewportUnavailable=viewModel::unavailable,viewportRetryToken=0,
            onSelectBar={id->if(selectedId==id)onOpenBar(id) else selectedId=id},
            onViewportChanged={viewport->viewModel.load(viewport)},
            recenterToken=recenterToken,onMapViewChanged={mapView=it},
            modifier=Modifier.fillMaxSize(),p18Markers=true,
            showOriginMarker=location!=null,
            p18MarkerSubtitle={id->
                bars.firstOrNull{it.barId==id}?.let{bar->
                    location?.let{p18Distance(distanceMeters(it,bar.location).toInt())}
                }
            })
        if(listVisible && !searchVisible) {
            Column(Modifier.fillMaxSize().background(P18Bg)
                .padding(top=72.dp).testTag("customer-map-list")) {
                Row(Modifier.fillMaxWidth().padding(start=20.dp,end=20.dp,top=16.dp,bottom=4.dp),
                    horizontalArrangement=Arrangement.SpaceBetween,
                    verticalAlignment=Alignment.CenterVertically) {
                    Text("이 지도 영역의 매장 ${ordered.size}곳",fontSize=18.sp,
                        fontWeight=FontWeight.SemiBold,color=P18Text)
                    P18SortTrigger((if(location==null)P18Sort.UPDATED else sort).label,
                        {showSort=true})
                }
                when(state) {
                    P18ExploreState.TooWide->P18FailureBody("지도를 확대하면 매장이 보여요",
                        "지도를 조금 더 확대해 주세요.","지도 보기",
                        BmIconId.SEARCH,{listVisible=false},Modifier.weight(1f))
                    P18ExploreState.Error->P18FailureBody("매장을 불러오지 못했어요",
                        "연결을 확인하고 다시 시도해 주세요.","다시 시도",
                        BmIconId.ERROR,viewModel::retry,Modifier.weight(1f),primary=true)
                    is P18ExploreState.Ready -> {
                        if(ordered.isEmpty()) P18FailureBody("이 지역에는 아직 등록된 매장이 없어요",
                            "지금은 관악구 매장부터 모으고 있어요.",
                            "관악구로 이동",BmIconId.BAR_PIN,
                            {listVisible=false;goToGwanak=true;recenterToken++},
                            modifier=Modifier.weight(1f))
                        else LazyColumn(Modifier.fillMaxSize().padding(horizontal=20.dp)) {
                            items(ordered,key={it.barId}){bar->
                                P18BrowseRow(bar,location,
                                    onClick={onOpenBar(bar.barId)})
                                Box(Modifier.fillMaxWidth().height(1.dp).background(P18Line))
                            }
                        }
                    }
                    else->Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center) {
                        CircularProgressIndicator(color=P18Gold)
                    }
                }
            }
        }
        if(!listVisible && !searchVisible) {
            when(state) {
                P18ExploreState.TooWide -> {
                    Row(Modifier.align(Alignment.TopCenter).padding(top=84.dp)
                        .background(P18Bg,RoundedCornerShape(24.dp))
                        .padding(horizontal=16.dp,vertical=10.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        BmIcon(BmIconId.SEARCH,null,Modifier.size(18.dp),tint=P18Gold)
                        Text("지도를 확대하면 매장이 보여요",color=P18Text,fontSize=14.sp)
                    }
                }
                P18ExploreState.Error -> {
                    P18MapErrorCard("매장을 불러오지 못했어요",
                        "연결을 확인하고 다시 시도해 주세요.",
                        "다시 시도",viewModel::retry,
                        Modifier.align(Alignment.BottomCenter).padding(16.dp))
                }
                is P18ExploreState.Ready -> if(bars.isEmpty()) {
                    P18MapErrorCard("이 지역에는 아직 등록된 매장이 없어요",
                        "지금은 관악구 매장부터 모으고 있어요.",
                        "관악구로 이동",{goToGwanak=true;recenterToken++},
                        Modifier.align(Alignment.BottomCenter).padding(16.dp),
                        error=false)
                }
                else {
                    LazyRow(Modifier.align(Alignment.BottomCenter)
                        .fillMaxWidth().padding(bottom=24.dp),
                        horizontalArrangement=Arrangement.spacedBy(8.dp),
                        contentPadding=PaddingValues(horizontal=16.dp)) {
                        items(ordered,key={it.barId}){bar->
                            Row(Modifier.width(265.dp).heightIn(min=88.dp)
                                .background(P18Bg,RoundedCornerShape(12.dp))
                                .clickable {
                                    if(selectedId==bar.barId)onOpenBar(bar.barId)
                                    else selectedId=bar.barId
                                }.padding(horizontal=10.dp,vertical=8.dp),
                                verticalAlignment=Alignment.CenterVertically,
                                horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                                if(!bar.coverThumbnailUrl.isNullOrBlank())
                                    P18RemoteBarPhoto(bar.coverThumbnailUrl,Modifier.size(54.dp))
                                else P18Photo(size=54.dp)
                                Column(Modifier.weight(1f)) {
                                    Text(bar.name,color=P18Text,fontSize=16.sp,
                                        fontWeight=FontWeight.SemiBold,maxLines=1,
                                        overflow=TextOverflow.Ellipsis)
                                    if(location!=null)Text(p18Distance(
                                        distanceMeters(location!!,bar.location).toInt()),
                                        color=P18Text,fontSize=13.sp)
                                    Text(bar.menuUpdatedAt?.let{
                                        "메뉴 ${p18MenuUpdated(it)} 기준"} ?:"메뉴 정보 없음",
                                        color=P18Muted,fontSize=12.sp)
                                }
                            }
                        }
                    }
                }
                else -> Unit
            }
            Box(Modifier.align(Alignment.BottomEnd)
                .padding(bottom=126.dp,end=16.dp)
                .size(48.dp)
                .clickable(onClick=::requestCurrentLocation)
                .testTag("customer-map-recenter"),contentAlignment=Alignment.Center) {
                BmIcon(BmIconId.LOCATION,"내 위치로",Modifier.size(23.dp),tint=P18Gold)
            }
        }
        if(searchVisible) {
            Column(Modifier.fillMaxSize().background(P18Bg)
                .padding(top=76.dp).testTag("customer-map-place-search")) {
                when(val result=placeState) {
                    MapPlaceSearchState.Idle -> Text("역, 매장 이름 또는 주소를 입력해 주세요.",
                        Modifier.padding(20.dp),color=P18Muted,fontSize=14.sp)
                    MapPlaceSearchState.Loading -> Box(Modifier.fillMaxWidth().padding(32.dp),
                        contentAlignment=Alignment.Center) {
                        CircularProgressIndicator(color=P18Gold)
                    }
                    is MapPlaceSearchState.Error -> P18FailureBody(
                        "그 장소를 찾지 못했어요",
                        "역 이름, 매장 이름, 주소로\n다시 찾아보세요.",
                        "검색어 고치기",BmIconId.BAR_PIN,
                        {searchText="";searchViewModel.dismissResults()})
                    is MapPlaceSearchState.Results -> {
                        if(result.places.isEmpty())P18FailureBody("그 장소를 찾지 못했어요",
                            "역 이름, 매장 이름, 주소로\n다시 찾아보세요.",
                            "검색어 고치기",BmIconId.BAR_PIN,
                            {searchText="";searchViewModel.dismissResults()})
                        else LazyColumn(Modifier.fillMaxSize().padding(horizontal=20.dp)) {
                            val registered=result.places.filter{it.barId!=null}
                            val locations=result.places.filter{it.barId==null}
                            listOf("등록된 매장" to registered,"장소" to locations).forEach{ (header,places)->
                                if(places.isNotEmpty()) {
                                    item {Text(header,Modifier.padding(top=20.dp,bottom=4.dp),
                                        color=P18Muted,fontSize=14.sp)}
                                    items(places){place->
                                        Row(Modifier.fillMaxWidth().heightIn(min=64.dp)
                                            .clickable{
                                                if(searchViewModel.select(place)) {
                                                    searchVisible=false;listVisible=false
                                                }
                                            }.padding(vertical=8.dp),
                                            verticalAlignment=Alignment.CenterVertically,
                                            horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                                            Box(Modifier.size(40.dp)
                                                .background(P18Surface,RoundedCornerShape(12.dp)),
                                                contentAlignment=Alignment.Center) {
                                                BmIcon(if(place.barId!=null)BmIconId.GLASS
                                                    else BmIconId.BAR_PIN,null,Modifier.size(22.dp),
                                                    tint=P18Muted)
                                            }
                                            Column(Modifier.weight(1f),
                                                verticalArrangement=Arrangement.spacedBy(1.dp)) {
                                                Text(place.name,color=P18Text,fontSize=16.sp,
                                                    fontWeight=FontWeight.SemiBold)
                                                Text(place.address,color=P18Muted,fontSize=13.sp,
                                                    maxLines=1,overflow=TextOverflow.Ellipsis)
                                            }
                                        }
                                        Box(Modifier.fillMaxWidth().height(1.dp).background(P18Line))
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().padding(start=12.dp,end=12.dp,top=12.dp),
            verticalAlignment=Alignment.CenterVertically,
            horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            P18Back(::back,dark=!listVisible)
            if(searchVisible) {
                P18SearchField(searchText,{searchText=it},
                    {searchViewModel.search(searchText)},placeholder="역 · 매장 이름 · 주소",
                    modifier=Modifier.weight(1f))
            } else {
                Row(Modifier.weight(1f).height(48.dp)
                    .background(if(listVisible)P18Surface else P18Bg,RoundedCornerShape(12.dp))
                    .clickable{searchVisible=true;searchViewModel.dismissResults()}
                    .padding(horizontal=12.dp),
                    verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    BmIcon(BmIconId.SEARCH,null,Modifier.size(20.dp),tint=P18Muted)
                    Text("역 · 매장 이름 · 주소",color=BottleMapPalette.textMuted,
                        fontSize=15.sp,maxLines=1,overflow=TextOverflow.Ellipsis)
                }
                P18ModeButton(if(listVisible)"지도" else "목록",
                    {listVisible=!listVisible},dark=!listVisible)
            }
        }
    }
}

@Composable
private fun P18BrowseRow(bar:MapBar,origin:NearbyCoordinate?,onClick:()->Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min=96.dp)
        .clickable(onClick=onClick).padding(vertical=12.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(12.dp)) {
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                Text(bar.name,color=P18Text,fontSize=16.sp,fontWeight=FontWeight.SemiBold,
                    maxLines=1,overflow=TextOverflow.Ellipsis)
                origin?.let {Text(p18Distance(
                    distanceMeters(it,bar.location).toInt()),
                    fontSize=12.sp,color=P18Muted)}
            }
            Text(bar.address,color=P18Text,fontSize=13.sp,
                maxLines=1,overflow=TextOverflow.Ellipsis)
            Text(bar.menuUpdatedAt?.let{"메뉴 ${p18MenuUpdated(it)} 기준"}
                ?:"메뉴 정보 없음",fontSize=12.sp,color=P18Muted)
        }
        if(!bar.coverThumbnailUrl.isNullOrBlank())
            P18RemoteBarPhoto(bar.coverThumbnailUrl,Modifier.size(64.dp))
        else P18Photo()
    }
}

@Composable
private fun P18MapErrorCard(
    title:String,description:String,action:String,onAction:()->Unit,
    modifier:Modifier=Modifier,error:Boolean=true,
) {
    Column(modifier.fillMaxWidth()
        .background(P18Bg,RoundedCornerShape(16.dp))
        .border(1.dp,P18Line,RoundedCornerShape(16.dp))
        .padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Row(verticalAlignment=Alignment.Top,
            horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            if(error)BmIcon(BmIconId.ERROR,null,Modifier.size(22.dp),
                tint=BottleMapPalette.error)
            Column(verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Text(title,color=P18Text,fontSize=16.sp,
                    lineHeight=24.sp,fontWeight=FontWeight.SemiBold)
                Text(description,color=P18Muted,fontSize=14.sp,lineHeight=20.sp)
            }
        }
        P18Action(action,onAction,primary=true,
            modifier=Modifier.fillMaxWidth().height(48.dp))
    }
}
