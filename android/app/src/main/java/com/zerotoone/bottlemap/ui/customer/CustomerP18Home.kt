
package com.zerotoone.bottlemap.ui.customer

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.compose.runtime.DisposableEffect
import androidx.lifecycle.ViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewModelScope
import androidx.lifecycle.viewmodel.compose.viewModel
import com.zerotoone.bottlemap.data.CustomerDiscoverySource
import com.zerotoone.bottlemap.data.Repositories
import com.zerotoone.bottlemap.network.PopularProductDto
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.theme.BottleMapPalette
import com.zerotoone.bottlemap.ui.common.BmIconId
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import org.json.JSONArray

internal sealed interface P18PopularState {
    data object Loading: P18PopularState
    data class Ready(val items: List<PopularProductDto>): P18PopularState
    data object Error: P18PopularState
}

/** Live §3.17 popular API, isolated failure cannot block the home screen. */
internal class P18PopularViewModel(
    private val repository:CustomerDiscoverySource=Repositories.customer,
): ViewModel() {
    private val mutable = MutableStateFlow<P18PopularState>(P18PopularState.Loading)
    val state = mutable.asStateFlow()
    private var initialized = false
    fun load(force: Boolean = false) {
        if (initialized && !force) return
        initialized = true
        mutable.value = P18PopularState.Loading
        viewModelScope.launch {
            try {
                mutable.value = P18PopularState.Ready(
                    repository.popularProducts(limit=10).items)
            } catch (cancelled: CancellationException) {
                throw cancelled
            } catch (_: Exception) { mutable.value = P18PopularState.Error }
        }
    }
}

private const val RECENT_KEY = "customer-p18-recent-v1"
internal fun readP18Recents(context: Context): List<String> = runCatching {
    val raw = context.getSharedPreferences("bottlemap-search-history", Context.MODE_PRIVATE)
        .getString(RECENT_KEY, "[]").orEmpty()
    val array = JSONArray(raw)
    (0 until array.length()).map { array.getString(it) }
        .filter { it.isNotBlank() && it.length <= 100 }.distinct().take(8)
}.getOrDefault(emptyList())

internal fun rememberP18Search(context: Context, input: String): List<String> {
    val normalized = input.trim().take(100)
    if (normalized.isBlank()) return readP18Recents(context)
    val next = (listOf(normalized) + readP18Recents(context).filterNot { it == normalized }).take(8)
    val json = JSONArray().apply { next.forEach { put(it) } }.toString()
    context.getSharedPreferences("bottlemap-search-history", Context.MODE_PRIVATE)
        .edit().putString(RECENT_KEY,json).apply()
    return next
}

internal fun clearP18Recents(context: Context) {
    context.getSharedPreferences("bottlemap-search-history", Context.MODE_PRIVATE)
        .edit().remove(RECENT_KEY).apply()
}

@Composable
internal fun CustomerP18Home(
    onSearch: (String, String) -> Unit,
    onPopular: (String) -> Unit,
    onAccount: () -> Unit,
    onMap: () -> Unit,
    popularViewModel: P18PopularViewModel = viewModel(),
) {
    val context = LocalContext.current
    var search by rememberSaveable { mutableStateOf("") }
    // Home must always show an empty query after returning from any other route.
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            if (event == Lifecycle.Event.ON_RESUME) search = ""
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }
    var recent by remember { mutableStateOf(readP18Recents(context)) }
    val popular by popularViewModel.state.collectAsStateWithLifecycle()
    LaunchedEffect(popularViewModel) { popularViewModel.load() }
    fun launch(term: String, source: String) {
        val trimmed = term.trim()
        if (trimmed.isBlank() || trimmed.length > 100) return
        recent = rememberP18Search(context,trimmed)
        onSearch(trimmed,source)
    }
    Column(Modifier.fillMaxSize().background(P18Bg).testTag("customer-home")) {
        Row(Modifier.fillMaxWidth().height(56.dp).padding(start = 20.dp,end=8.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.SpaceBetween) {
            Text("BottleMap",style=MaterialTheme.typography.titleMedium,
                fontSize = 18.sp,fontWeight=FontWeight.Bold,color=P18Gold)
            Box(Modifier.size(48.dp).clickable(onClick=onAccount)
                .testTag("customer-account-entry"), contentAlignment=Alignment.Center) {
                BmIcon(BmIconId.ACCOUNT,"마이페이지",Modifier.size(24.dp),tint=P18Text)
            }
        }
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(top=8.dp,bottom=24.dp),
            verticalArrangement=Arrangement.spacedBy(24.dp)) {
            Column(Modifier.fillMaxWidth().padding(horizontal=20.dp),
                verticalArrangement=Arrangement.spacedBy(16.dp)) {
                Text("어떤 위스키를\n마실까요?",
                    style=MaterialTheme.typography.headlineSmall,
                    fontSize=24.sp,lineHeight=32.sp,color=P18Text)
                P18SearchField(search, {search=it}, {launch(search,"input")},
                    modifier=Modifier.fillMaxWidth())
            }
            Column(Modifier.fillMaxWidth().padding(horizontal=20.dp),
                verticalArrangement=Arrangement.spacedBy(8.dp)) {
                if (recent.isNotEmpty()) {
                    Row(Modifier.fillMaxWidth().heightIn(min=40.dp),
                        verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.SpaceBetween) {
                        Text("최근 검색",fontSize=14.sp,color=P18Muted)
                        TextButton(onClick={ clearP18Recents(context); recent=emptyList() }) {
                            Text("모두 지우기",fontSize=13.sp,color=P18Muted)
                        }
                    }
                } else {
                    Text("이렇게 찾아보세요",fontSize=14.sp,color=P18Muted)
                }
                Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    val examples = if (recent.isEmpty()) listOf("글렌피딕","Glenfiddich 12") else recent.take(3)
                    examples.forEach { term ->
                        Box(Modifier.height(40.dp)
                            .background(if(recent.isEmpty())P18Bg else P18Surface,
                                RoundedCornerShape(20.dp))
                            .border(1.dp,if(recent.isEmpty())BottleMapPalette.outline else P18Line,
                                RoundedCornerShape(20.dp))
                            .clickable {launch(term,if(recent.isEmpty())"input" else "recent")}
                            .padding(horizontal=14.dp),
                            contentAlignment=Alignment.Center) {
                            Text(term,color=P18Text,fontSize=14.sp,fontWeight=FontWeight.Medium,
                                maxLines=1)
                        }
                    }
                }
            }
            Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {
                val items=(popular as? P18PopularState.Ready)?.items.orEmpty()
                if (items.isNotEmpty()) {
                    Text("요즘 많이 찾는 위스키",
                        Modifier.padding(horizontal=20.dp),fontSize=16.sp,
                        fontWeight=FontWeight.SemiBold,color=P18Text)
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())
                        .padding(horizontal=20.dp),
                        horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                        items.forEach { product ->
                            Column(Modifier.width(112.dp).heightIn(min=160.dp)
                                .background(P18Surface,RoundedCornerShape(16.dp))
                                .clickable { onPopular(product.productId) }
                                .testTag("customer-popular-${product.productId}")
                                .padding(start=12.dp,end=12.dp,top=14.dp,bottom=12.dp),
                                horizontalAlignment=Alignment.CenterHorizontally,
                                verticalArrangement=Arrangement.spacedBy(10.dp)) {
                                P18Bottle(product.displayName)
                                Column(horizontalAlignment=Alignment.CenterHorizontally,
                                    verticalArrangement=Arrangement.spacedBy(2.dp)) {
                                    Text(product.displayName,color=P18Text,fontSize=14.sp,
                                        lineHeight=20.sp,fontWeight=FontWeight.SemiBold,
                                        textAlign=TextAlign.Center)
                                    Text("매장 ${product.barCount}곳",color=P18Muted,
                                        fontSize=12.sp,lineHeight=18.sp,
                                        textAlign=TextAlign.Center)
                                }
                            }
                        }
                    }
                } else if (popular is P18PopularState.Error) {
                    Row(Modifier.fillMaxWidth().padding(horizontal=20.dp),
                        horizontalArrangement=Arrangement.SpaceBetween,
                        verticalAlignment=Alignment.CenterVertically) {
                        Text("요즘 많이 찾는 위스키",color=P18Muted,fontSize=16.sp)
                        TextButton(onClick={popularViewModel.load(force=true)}) {
                            Text("다시 시도",color=P18Gold)
                        }
                    }
                }
            }
            Row(Modifier.fillMaxWidth().padding(horizontal=20.dp)
                .heightIn(min=72.dp).background(P18Surface,RoundedCornerShape(16.dp))
                .clickable(onClick=onMap).testTag("customer-home-map")
                .padding(horizontal=16.dp,vertical=12.dp),
                verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                Box(Modifier.size(48.dp).background(P18Elevated,RoundedCornerShape(12.dp)),
                    contentAlignment=Alignment.Center) {
                    BmIcon(BmIconId.MAP,null,Modifier.size(24.dp),tint=P18Gold)
                }
                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(2.dp)) {
                    Text("지도로 보기",color=P18Text,fontSize=16.sp,
                        fontWeight=FontWeight.SemiBold)
                    Text("지도를 움직여 매장과 메뉴를 찾아요",color=P18Muted,
                        fontSize=13.sp,lineHeight=20.sp)
                }
                Text("›",fontSize=22.sp,color=P18Muted)
            }
        }
    }
}
