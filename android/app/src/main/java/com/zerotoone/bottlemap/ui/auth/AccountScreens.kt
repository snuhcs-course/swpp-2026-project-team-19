
package com.zerotoone.bottlemap.ui.auth

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.ui.graphics.Color
import androidx.compose.runtime.Composable
import androidx.compose.runtime.produceState
import kotlinx.coroutines.CancellationException
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zerotoone.bottlemap.data.OwnerRepository
import com.zerotoone.bottlemap.ui.common.BmIcon
import com.zerotoone.bottlemap.ui.common.BmIconId
import com.zerotoone.bottlemap.ui.customer.P18Bg
import com.zerotoone.bottlemap.ui.customer.P18Surface
import com.zerotoone.bottlemap.ui.customer.P18Elevated
import com.zerotoone.bottlemap.ui.customer.P18Line
import com.zerotoone.bottlemap.ui.customer.P18Muted
import com.zerotoone.bottlemap.ui.customer.P18Gold
import com.zerotoone.bottlemap.ui.customer.P18Text
import com.zerotoone.bottlemap.ui.customer.P18Back
import com.zerotoone.bottlemap.ui.customer.P18Action

/**
 * ACTION_FIRST P18 HTML pp.23-27. Back button on My Page is an explicit
 * user-approved correction to the source PDF (both guest and signed-in states).
 * Google auth remains owned by AuthViewModel and Credential Manager.
 */
private sealed interface OwnerAreaLoad {
    data object Loading : OwnerAreaLoad
    data class Ready(val hasBars: Boolean, val hasApplication: Boolean) : OwnerAreaLoad
    data class Error(val message: String) : OwnerAreaLoad
}

@Composable
fun AccountScreen(
    state: AuthUiState,
    onBack: () -> Unit,
    onOpenLogin: () -> Unit,
    onLogout: () -> Unit,
    onRetryAccount: () -> Unit,
    onOpenOwner: () -> Unit = {},
) {
    // Owner access is based on the authenticated server account, never demo fixture data.
    val signedInUser=(state as? AuthUiState.SignedIn)?.user
    var ownerRetryNonce by remember(signedInUser?.userId) { mutableStateOf(0) }
    val ownerStatus by produceState<OwnerAreaLoad>(
        initialValue=OwnerAreaLoad.Loading,
        key1=signedInUser?.userId, key2=ownerRetryNonce,
    ) {
        value=OwnerAreaLoad.Loading
        if(signedInUser==null) {
            value=OwnerAreaLoad.Ready(false,false)
        } else try {
            val owner=OwnerRepository()
            val bars=owner.getOwnedBars()
            val applications=owner.getMyApplications()
            value=OwnerAreaLoad.Ready(
                bars.isNotEmpty(), applications.any {
                    it.status=="pending" || it.status=="rejected"
                })
        } catch(cancelled: CancellationException) {
            throw cancelled
        } catch(error: Exception) {
            value=OwnerAreaLoad.Error(error.message ?: "매장 상태를 확인하지 못했어요.")
        }
    }
    val area=(ownerStatus as? OwnerAreaLoad.Ready)
    val hasArea=area?.let { it.hasBars || it.hasApplication } == true
    val subtitle=when {
        area?.hasBars==true -> "매장을 관리해 주세요"
        area?.hasApplication==true -> "매장 등록 신청 상태를 확인하세요"
        else -> "매장 등록 상태를 확인하세요"
    }
    var infoDialog by remember {mutableStateOf<String?>(null)}
    if(infoDialog!=null) AlertDialog(onDismissRequest={infoDialog=null},
        title={Text(infoDialog.orEmpty())},
        text={Text("이 기능은 준비 중이에요.")},
        confirmButton={TextButton(onClick={infoDialog=null}) {Text("확인")}})
    Column(Modifier.fillMaxSize().background(P18Bg).testTag("customer-my-page")) {
        AccountHeader("마이페이지",onBack)
        Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState())
            .padding(start=20.dp,end=20.dp,top=16.dp,bottom=24.dp),
            verticalArrangement=Arrangement.spacedBy(0.dp)) {
            val user=(state as? AuthUiState.SignedIn)?.user
            Row(Modifier.fillMaxWidth().heightIn(min=56.dp)
                .then(if(user==null)Modifier.clickable(onClick=onOpenLogin) else Modifier),
                verticalAlignment=Alignment.CenterVertically,
                horizontalArrangement=Arrangement.spacedBy(14.dp)) {
                Box(Modifier.size(48.dp).background(P18Elevated,CircleShape),
                    contentAlignment=Alignment.Center) {
                    BmIcon(BmIconId.ACCOUNT,null,Modifier.size(26.dp),tint=P18Text)
                }
                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(2.dp)) {
                    Text(user?.displayName?.takeIf{it.isNotBlank()}
                        ?:user?.email?.substringBefore('@')?.takeIf{it.isNotBlank()}
                        ?: "로그인하기",
                        fontSize=22.sp,lineHeight=30.sp,fontWeight=FontWeight.Bold,color=P18Text)
                    Text(user?.email ?: "Google 계정으로 로그인",
                        fontSize=14.sp,lineHeight=20.sp,color=P18Muted)
                }
                if(user==null) Text("›",color=P18Muted,fontSize=22.sp)
            }
            if(user!=null && ownerStatus is OwnerAreaLoad.Loading) {
                Row(Modifier.fillMaxWidth().padding(top=28.dp),
                    verticalAlignment=Alignment.CenterVertically) {
                    CircularProgressIndicator(Modifier.size(20.dp))
                    Spacer(Modifier.width(12.dp))
                    Text("매장 상태를 확인하고 있어요.", color=P18Muted)
                }
            }
            if(user!=null && ownerStatus is OwnerAreaLoad.Error) {
                Column(Modifier.fillMaxWidth().padding(top=28.dp),
                    verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    Text("매장 상태를 불러오지 못했어요.", color=P18Text)
                    Text((ownerStatus as OwnerAreaLoad.Error).message,
                        color=P18Muted, fontSize=13.sp)
                    TextButton(onClick={ ownerRetryNonce++ }) { Text("다시 시도") }
                }
            }
            if(user!=null && hasArea) {
                Row(Modifier.fillMaxWidth().padding(top=28.dp).heightIn(min=96.dp)
                    .background(androidx.compose.ui.graphics.Color(0xFF2A2521),
                        RoundedCornerShape(16.dp))
                    .border(1.dp,androidx.compose.ui.graphics.Color(0xFF8C6C4A),
                        RoundedCornerShape(16.dp))
                    .clickable(onClick=onOpenOwner).testTag("customer-owner-entry")
                    .padding(horizontal=16.dp,vertical=18.dp),
                    verticalAlignment=Alignment.CenterVertically,
                    horizontalArrangement=Arrangement.spacedBy(14.dp)) {
                    Box(Modifier.size(40.dp)
                        .background(androidx.compose.ui.graphics.Color(0xFF5C4329),
                            RoundedCornerShape(10.dp)),contentAlignment=Alignment.Center) {
                        BmIcon(BmIconId.MANAGE_BAR,null,Modifier.size(23.dp),tint=P18Gold)
                    }
                    Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text("내 매장 관리",color=P18Text,fontSize=17.sp,
                            lineHeight=24.sp,fontWeight=FontWeight.Bold)
                        Text(subtitle,color=P18Muted,fontSize=14.sp)
                    }
                    Text("›",color=P18Muted,fontSize=21.sp)
                }
            }
            Column(Modifier.fillMaxWidth().padding(top=28.dp)) {
                AccountNavRow("공지사항"){infoDialog="공지사항"}
                AccountNavRow("문의하기"){infoDialog="문의하기"}
                if(user!=null) AccountNavRow("로그아웃",onLogout)
                if(state is AuthUiState.SignInError) AccountNavRow(
                    "다시 로그인하기",if(state.canRetryProfile)onRetryAccount else onOpenLogin)
            }
            if(!hasArea && (user==null || ownerStatus is OwnerAreaLoad.Ready)) {
                Row(Modifier.fillMaxWidth().padding(top=32.dp),
                    horizontalArrangement=Arrangement.Center,
                    verticalAlignment=Alignment.CenterVertically) {
                    Text("사장님이신가요?",color=P18Muted,fontSize=15.sp)
                    Spacer(Modifier.width(6.dp))
                    Row(Modifier.heightIn(min=48.dp)
                        .clickable(onClick=if(user==null)onOpenLogin else onOpenOwner),
                        verticalAlignment=Alignment.CenterVertically) {
                        Text("매장 등록하기",fontSize=15.sp,color=P18Gold,
                            fontWeight=FontWeight.Bold,
                            textDecoration=androidx.compose.ui.text.style.TextDecoration.Underline)
                        Text("›",color=P18Gold)
                    }
                }
            }
            // Google Credential Manager owns the account picker. No auth
            // progress animation is shown behind the system dialog (v20).
        }
    }
}

@Composable
private fun AccountNavRow(label:String,onClick:()->Unit) {
    Row(Modifier.fillMaxWidth().height(56.dp).clickable(onClick=onClick)
        .testTag("customer-account-${label}")
        .padding(horizontal=0.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.SpaceBetween) {
        Text(label,color=P18Text,fontSize=16.sp)
        Text("›",color=P18Muted,fontSize=22.sp)
    }
    Box(Modifier.fillMaxWidth().height(1.dp)
        .background(androidx.compose.ui.graphics.Color(0xFF3F3732)))
}

/** Existing Google credential exchange; this only changes visual presentation. */
@Composable
fun GoogleLoginScreen(
    state: AuthUiState,
    authViewModel: AuthViewModel,
    onBack: () -> Unit,
    onContinueGuest: () -> Unit,
) {
    Column(Modifier.fillMaxSize().background(P18Bg).testTag("customer-google-login")) {
        AccountHeader("로그인",onBack)
        Column(Modifier.fillMaxSize().padding(horizontal=20.dp,vertical=12.dp),
            verticalArrangement=Arrangement.spacedBy(20.dp)) {
            Text("Google 계정으로 선택적으로 로그인해요.",
                style=MaterialTheme.typography.headlineSmall,fontSize=24.sp,
                lineHeight=34.sp,color=P18Text)
            if(state is AuthUiState.SignInError) {
                Row(verticalAlignment=Alignment.Top,
                    horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                    BmIcon(BmIconId.ERROR,null,Modifier.size(18.dp),
                        tint=Color(0xFFFFB4AB))
                    Text("로그인을 완료하지 못했습니다. 설정과 네트워크를 확인한 뒤 다시 시도해 주세요.",
                        fontSize=14.sp,lineHeight=21.sp,color=Color(0xFFFFB4AB))
                }
            }
            if(state is AuthUiState.Initializing || state is AuthUiState.SigningIn) {
                // Static state copy only; never animate a spinner under Google picker.
                Text("로그인 중이에요",color=P18Muted)
            }
            Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
                GoogleSignInButton(viewModel=authViewModel,
                    enabled=state is AuthUiState.Guest || state is AuthUiState.SignInError)
                Box(Modifier.fillMaxWidth().height(52.dp)
                    .border(1.dp,com.zerotoone.bottlemap.ui.theme.BottleMapPalette.outline,
                        RoundedCornerShape(12.dp))
                    .clickable(onClick=onContinueGuest),contentAlignment=Alignment.Center) {
                    Text("취소하고 Guest로 계속",color=P18Text,fontSize=15.sp,
                        fontWeight=FontWeight.SemiBold)
                }
            }
        }
    }
}

/** Explicit P18 correction: back icon consumes 48dp at the exact original x=8. */
@Composable
private fun AccountHeader(title:String,onBack:()->Unit) {
    Row(Modifier.fillMaxWidth().height(72.dp)
        .padding(start=8.dp,end=20.dp,top=8.dp,bottom=8.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(4.dp)) {
        P18Back(onBack)
        Text(title,color=P18Text,fontSize=18.sp,lineHeight=26.sp,
            fontFamily=MaterialTheme.typography.headlineSmall.fontFamily,
            fontWeight=FontWeight.Bold)
    }
}
