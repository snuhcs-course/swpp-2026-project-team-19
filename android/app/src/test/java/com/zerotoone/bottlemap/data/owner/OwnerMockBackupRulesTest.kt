package com.zerotoone.bottlemap.data.owner

import java.io.File
import javax.xml.parsers.DocumentBuilderFactory
import org.junit.Assert.assertTrue
import org.junit.Test
import org.w3c.dom.Element

/**
 * Prevent app-private Mock contact/draft data from accidentally entering cloud backup
 * or Android's device-to-device transfer after future preference name changes.
 */
class OwnerMockBackupRulesTest {
    private fun hasMockExclusion(fileName: String, sectionName: String? = null): Boolean {
        val xml = File("src/main/res/xml/$fileName")
        val doc = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(xml)
        val section = if (sectionName == null) doc.documentElement else
            doc.getElementsByTagName(sectionName).item(0)
        requireNotNull(section) { "Missing $sectionName in $fileName" }
        val exclusions = (section as Element).getElementsByTagName("exclude")
        return (0 until exclusions.length).any { index ->
            val element = exclusions.item(index) as Element
            element.getAttribute("domain") == "sharedpref" &&
                element.getAttribute("path") == "$OWNER_MOCK_PREFERENCES_NAME.xml"
        }
    }

    @Test fun mockPreferencesAreExcludedFromCloudBackupAndDeviceTransfer() {
        assertTrue(hasMockExclusion("developer_camera_backup_rules.xml"))
        assertTrue(hasMockExclusion("developer_camera_data_extraction_rules.xml", "cloud-backup"))
        assertTrue(hasMockExclusion("developer_camera_data_extraction_rules.xml", "device-transfer"))
    }
}
