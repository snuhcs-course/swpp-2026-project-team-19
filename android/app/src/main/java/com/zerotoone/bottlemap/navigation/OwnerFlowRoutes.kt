package com.zerotoone.bottlemap.navigation

/**
 * Visual-only destinations transcribed from BottleMap_owner_flow_FINAL.html.
 * No fake barId, productId, menuImportId or backend state is generated here.
 * Replace UX preview routes with ID-scoped production routes as features are implemented.
 */
enum class OwnerFlowGroup(val slug: String, val title: String) {
    REGISTRATION("registration", "최초 등록 · 승인"),
    MANAGEMENT("management", "매장 관리"),
    PHOTO_REVIEW("photo-review", "사진 메뉴 등록 · 검수"),
}

enum class OwnerPage(val group: OwnerFlowGroup, val htmlId: String, val title: String) {
    REG_MYPAGE(OwnerFlowGroup.REGISTRATION, "mypage", "등록 전 마이페이지"),
    REG_INTRO(OwnerFlowGroup.REGISTRATION, "intro", "매장 등록 안내"),
    REG_METHOD(OwnerFlowGroup.REGISTRATION, "method", "등록 방식 선택"),
    REG_READING(OwnerFlowGroup.REGISTRATION, "reading", "사업자등록증 읽기"),
    REG_BN(OwnerFlowGroup.REGISTRATION, "bn", "사업자등록번호"),
    REG_REP(OwnerFlowGroup.REGISTRATION, "rep", "대표자명"),
    REG_DATE(OwnerFlowGroup.REGISTRATION, "date", "개업일"),
    REG_BIZCHECK(OwnerFlowGroup.REGISTRATION, "bizcheck", "사업자 정보 확인"),
    REG_VERIFYING(OwnerFlowGroup.REGISTRATION, "verifying", "사업자 정보 검증"),
    REG_VERIFIED(OwnerFlowGroup.REGISTRATION, "verified", "검증 결과"),
    REG_BARNAME(OwnerFlowGroup.REGISTRATION, "barname", "매장 이름"),
    REG_BARPHOTO(OwnerFlowGroup.REGISTRATION, "barphoto", "대표 사진"),
    REG_ADDRESS(OwnerFlowGroup.REGISTRATION, "address", "주소"),
    REG_BARPHONE(OwnerFlowGroup.REGISTRATION, "barphone", "매장 전화번호"),
    REG_MENUS(OwnerFlowGroup.REGISTRATION, "menus", "최초 메뉴판 사진"),
    REG_CONTACT(OwnerFlowGroup.REGISTRATION, "contact", "신청 연락처"),
    REG_REVIEW(OwnerFlowGroup.REGISTRATION, "review", "등록 신청 검토"),
    REG_DONE(OwnerFlowGroup.REGISTRATION, "done", "등록 신청 완료"),
    REG_MYPAGE2(OwnerFlowGroup.REGISTRATION, "mypage2", "신청 후 마이페이지"),
    REG_MANAGE(OwnerFlowGroup.REGISTRATION, "manage", "신청·관리 상태"),
    REG_REJECTED(OwnerFlowGroup.REGISTRATION, "manage-rejected", "승인 거절"),
    MGR_MY(OwnerFlowGroup.MANAGEMENT, "my", "내 매장 관리"),
    MGR_LIST(OwnerFlowGroup.MANAGEMENT, "list", "관리 매장 목록"),
    MGR_HOME(OwnerFlowGroup.MANAGEMENT, "home", "Owner 홈"),
    MGR_STATUS(OwnerFlowGroup.MANAGEMENT, "status", "영업 상태"),
    MGR_HOURS(OwnerFlowGroup.MANAGEMENT, "hours", "정규 영업시간"),
    MGR_TAGS(OwnerFlowGroup.MANAGEMENT, "tags", "매장 태그"),
    MGR_INFO(OwnerFlowGroup.MANAGEMENT, "info", "매장 정보"),
    MGR_PHOTOS(OwnerFlowGroup.MANAGEMENT, "photoEdit", "매장 사진 관리"),
    MGR_MENU(OwnerFlowGroup.MANAGEMENT, "menu", "메뉴 관리"),
    MGR_ITEM(OwnerFlowGroup.MANAGEMENT, "item", "메뉴 추가 · 수정"),
    MGR_PROMO(OwnerFlowGroup.MANAGEMENT, "promo", "할인 설정"),
    MGR_PHOTO(OwnerFlowGroup.MANAGEMENT, "photo", "메뉴판 사진 추가"),
    MGR_JOB(OwnerFlowGroup.MANAGEMENT, "job", "AI 처리 상태"),
    MGR_REVIEW(OwnerFlowGroup.MANAGEMENT, "review", "검수 요약"),
    MGR_AUTO(OwnerFlowGroup.MANAGEMENT, "reviewAutoList", "자동 인식 신규 목록"),
    MGR_LINE(OwnerFlowGroup.MANAGEMENT, "reviewLine", "추출 줄 검수"),
    MGR_PUBLISH(OwnerFlowGroup.MANAGEMENT, "reviewPublish", "게시 전 확인"),
    MGR_SUCCESS(OwnerFlowGroup.MANAGEMENT, "publishSuccess", "게시 완료"),
    MGR_PREVIEW(OwnerFlowGroup.MANAGEMENT, "preview", "고객 화면 미리보기"),
    PHOTO_START(OwnerFlowGroup.PHOTO_REVIEW, "s01", "사진 등록 진입"),
    PHOTO_PICK(OwnerFlowGroup.PHOTO_REVIEW, "s02", "사진 선택"),
    PHOTO_PROCESS(OwnerFlowGroup.PHOTO_REVIEW, "s03", "AI 분석 중"),
    PHOTO_PROCESS_ERROR(OwnerFlowGroup.PHOTO_REVIEW, "s03e", "AI 분석 실패"),
    PHOTO_SUMMARY(OwnerFlowGroup.PHOTO_REVIEW, "s04", "검수 요약"),
    PHOTO_AUTO(OwnerFlowGroup.PHOTO_REVIEW, "s04auto", "자동 신규 인식 목록"),
    PHOTO_ALREADY(OwnerFlowGroup.PHOTO_REVIEW, "s04b", "이미 있는 메뉴"),
    PHOTO_MATCH(OwnerFlowGroup.PHOTO_REVIEW, "s05", "상품 확인"),
    PHOTO_CANDIDATE(OwnerFlowGroup.PHOTO_REVIEW, "s06", "상품 후보 선택"),
    PHOTO_NEW(OwnerFlowGroup.PHOTO_REVIEW, "s07", "신규 상품 입력"),
    PHOTO_PRICE(OwnerFlowGroup.PHOTO_REVIEW, "s08", "가격 확인"),
    PHOTO_SEARCH(OwnerFlowGroup.PHOTO_REVIEW, "s09", "상품 검색"),
    PHOTO_INCOMPLETE(OwnerFlowGroup.PHOTO_REVIEW, "s10", "검수 미완료"),
    PHOTO_READY(OwnerFlowGroup.PHOTO_REVIEW, "s11", "게시 준비"),
    PHOTO_DECISIONS(OwnerFlowGroup.PHOTO_REVIEW, "s13sum", "검수 결정 재확인"),
    PHOTO_PUBLISHED(OwnerFlowGroup.PHOTO_REVIEW, "s12", "게시 결과"),
    PHOTO_PUBLISH_ERROR(OwnerFlowGroup.PHOTO_REVIEW, "s12e", "게시 실패"),
    PHOTO_OWNER_EDIT(OwnerFlowGroup.PHOTO_REVIEW, "owner-edit", "메뉴 편집 안내");

    val route: String get() = "owner/ux/${group.slug}/${htmlId}"

    fun next(): OwnerPage? =
        entries.filter { it.group == group }.let { pages ->
            pages.getOrNull(pages.indexOf(this) + 1)
        }
}

object OwnerRoutes {
    const val GRAPH = "owner"
    const val ENTRY = "owner/entry"
    const val COMPONENTS = "owner/components"
    const val LEGACY_UPLOAD = "owner/menu-upload"
    const val LEGACY_REVIEW = "owner/extraction-review/{menuImportId}"

    fun groupStart(group: OwnerFlowGroup): String =
        requireNotNull(OwnerPage.entries.firstOrNull { it.group == group }).route
}
