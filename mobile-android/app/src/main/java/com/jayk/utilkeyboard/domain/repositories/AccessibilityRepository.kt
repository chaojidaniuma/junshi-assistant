package com.jayk.utilkeyboard.domain.repositories

interface AccessibilityRepository {
    fun getLatestMessages(): List<String>
    fun getLastMessage(): String?
    fun checkForDatingApp(): Boolean?
}