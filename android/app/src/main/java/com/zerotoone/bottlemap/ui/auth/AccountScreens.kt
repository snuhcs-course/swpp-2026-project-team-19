
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
import androidx.compose.runtime.Composable
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
import com.zerotoone.bottlemap.data.owner.OwnerMockRuntime
import com.zerotoone.bottlemap.data.owner.MockOwnerLoadState
import com.zerotoone.bottlemap.data.owner.MockApplicationStatus
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
@Composable
fun AccountScreen(
    state: AuthUiState,
    onBack: () -> Unit,
    onOpenLogin: () -> Unit,
    onLogout: () -> Unit,
    onRetryAccount: () -> Unit,
    onOpenOwner: () -> Unit = {},
) {
    val ownerState by OwnerMockRuntime.repository(LocalContext.current).state.collectAsState()
    val owned=when(val s=ownerState) {
        is MockOwnerLoadState.Ready -> s.snapshot
        is MockOwnerLoadState.Empty -> s.snapshot
        else -> null
    }
    val hasArea=owned?.let{s-> s.bars.isNotEmpty() || s.applications.any {
        it.applicationId !in s.dismissedApplicationIds &&
            it.status in listOf(MockApplicationStatus.PENDING,MockApplicationStatus.REJECTED)
    }}==true
    val subtitle=when {
        owned?.bars?.isNotEmpty()==true->"매장을 관리해 주세요"
        owned?.applications?.any{it.status==MockApplicationStatus.PENDING}==true->
            "검토 중인 신청이 있어요"
        else->"매장 등록 상태를 확인하세요"
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
            if(!hasArea) {
                Row(Modifier.fillMaxWidth().padding(top=32.dp),
                    horizontalArrangement=Arrangement.Center,
                    verticalAlignment=Alignment.CenterVertically) {
                    Text("매장 사장님이신가요?",color=P18Muted,fontSize=15.sp)
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
            if(state is AuthUiState.Initializing || state is AuthUiState.SigningIn) {
                Spacer(Modifier.height(24.dp))
                CircularProgressIndicator(color=P18Gold)
            }
        }
    }
}

@Composable
private fun AccountNavRow(label:String,onClick:()->Unit) {
    Row(Modifier.fillMaxWidth().height(56.dp).clickable(onClick=onClick)
        .testTag("customer-account-${label}")
        .border(width=0.dp,color=P18Line)
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
        Column(Modifier.fillMaxSize().padding(horizontal=20.dp,vertical=24.dp),
            verticalArrangement=Arrangement.spacedBy(20.dp)) {
            Text("Google 계정으로 선택적으로 로그인해요.",
                style=MaterialTheme.typography.headlineSmall,fontSize=24.sp,
                lineHeight=32.sp,color=P18Text)
            Text("",
                fontSize=14.sp,lineHeight=21.sp,color=P18Muted)
            when(state) {
                AuthUiState.Initializing, AuthUiState.SigningIn -> {
                    Row(verticalAlignment=Alignment.CenterVertically,
                        horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                        CircularProgressIndicator(Modifier.size(24.dp),color=P18Gold)
                        Text("로그인 중이에요",color=P18Muted)
                    }
                }
                is AuthUiState.SignInError -> {
                    Text("로그인을 완료하지 못했습니다.",color=P18Text,fontSize=18.sp,
                        fontWeight=FontWeight.Bold)
                    Text(state.message,color=P18Muted,fontSize=14.sp)
                }
                else -> Unit
            }
            GoogleSignInButton(viewModel=authViewModel,
                enabled=state is AuthUiState.Guest || state is AuthUiState.SignInError)
            P18Action("취소하고 Guest로 계속",onContinueGuest,
                modifier=Modifier.fillMaxWidth())
        }
    }
}

/** Explicit P18 correction: back icon consumes 48dp at the exact original x=8. */
@Composable
private fun AccountHeader(title:String,onBack:()->Unit) {
    Row(Modifier.fillMaxWidth().heightIn(min=56.dp)
        .padding(start=8.dp,end=20.dp,top=8.dp),
        verticalAlignment=Alignment.CenterVertically,
        horizontalArrangement=Arrangement.spacedBy(4.dp)) {
        P18Back(onBack)
        Text(title,color=P18Text,fontSize=18.sp,lineHeight=26.sp,
            fontWeight=FontWeight.Bold)
    }
}
