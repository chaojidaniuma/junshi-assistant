package com.jayk.utilkeyboard.domain.repositories

import android.content.Context
import android.view.accessibility.AccessibilityManager
import com.jayk.utilkeyboard.domain.services.MessageAccessibilityService
import javax.inject.Inject

class AccessibilityRepositoryImpl @Inject constructor(
    private val context: Context,
    private val accessibilityManager: AccessibilityManager
) : AccessibilityRepository {

    override fun getLatestMessages(): List<String> {
        if (!accessibilityManager.isEnabled) {
            return emptyList()
        }

        val accessibilityService = MessageAccessibilityService.getInstance()
            ?: return emptyList()

        return accessibilityService.getLatestMessages()
    }

    override fun getLastMessage(): String? {
        if (!accessibilityManager.isEnabled) {
            return null
        }

        val accessibilityService = MessageAccessibilityService.getInstance()
            ?: return null

        return accessibilityService.getLastMessage()
    }

    override fun checkForDatingApp(): Boolean? {
        val accessibilityService = MessageAccessibilityService.getInstance()
            ?: return null
        return accessibilityService.getAppType()
    }
}