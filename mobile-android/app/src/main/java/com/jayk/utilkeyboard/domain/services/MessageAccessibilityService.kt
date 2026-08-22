package com.jayk.utilkeyboard.domain.services

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import dagger.hilt.android.AndroidEntryPoint
import android.util.Log

@AndroidEntryPoint
class MessageAccessibilityService : AccessibilityService() {
    companion object {
        private var instance: MessageAccessibilityService? = null
        private const val TAG = "MessageAccessibility"
        private const val WHATSAPP_PACKAGE = "com.whatsapp"
        private const val BUMBLE_PACKAGE = "com.bumble.app"
        private const val TINDER_PACKAGE = "com.tinder"
        private const val HINGE_PACKAGE = "co.hinge.app"

        fun getInstance(): MessageAccessibilityService? = instance
    }

    private val messagesList = mutableListOf<String>()
    private var isDatingApp: Boolean = false

    override fun onCreate() {
        super.onCreate()
        instance = this
    }

    override fun onDestroy() {
        super.onDestroy()
        instance = null
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        Log.d(TAG, "Received accessibility event: ${event.eventType}")

        if (event.packageName?.toString() != WHATSAPP_PACKAGE) {
            println(event.packageName?.toString())
            Log.d(TAG, "Ignoring event from package: ${event.packageName}")
            return
        }

        if (event.packageName?.toString() == HINGE_PACKAGE || event.packageName?.toString() == BUMBLE_PACKAGE || event.packageName?.toString() == TINDER_PACKAGE){
            isDatingApp = true
        }


            println("${event.packageName?.toString()} is the package")

        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED,
            AccessibilityEvent.TYPE_VIEW_SCROLLED -> {
                val rootNode = rootInActiveWindow
                if (rootNode == null) {
                    Log.e(TAG, "Root node is null")
                    return
                }

                try {
                    findWhatsAppMessages(rootNode)
                } catch (e: Exception) {
                    Log.e(TAG, "Error processing messages", e)
                } finally {
                    rootNode.recycle()
                }
            }

            else -> Log.d(TAG, "Unhandled event type: ${event.eventType}")
        }
    }

    private fun findWhatsAppMessages(node: AccessibilityNodeInfo) {
        try {
            if (node.viewIdResourceName?.contains("message_text") == true ||
                node.viewIdResourceName?.contains("conversation_text") == true
            ) {
                node.text?.toString()?.let { message ->
                    if (message.isNotBlank() && !messagesList.contains(message)) {
                        messagesList.add(message)
                        if (messagesList.size > 10) {
                            messagesList.removeAt(0)
                        }
                        Log.d(TAG, "New message captured: $message")
                    }
                }
            }

            for (i in 0 until node.childCount) {
                val child = node.getChild(i) ?: continue
                try {
                    findWhatsAppMessages(child)
                } finally {
                    child.recycle()
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error processing node", e)
        }
    }

    fun getLatestMessages(): List<String> = messagesList.toList()

    fun getLastMessage(): String? = messagesList.lastOrNull()

    fun getAppType(): Boolean = isDatingApp

    override fun onServiceConnected() {
        super.onServiceConnected()
        Log.d(TAG, "Accessibility Service Connected")
        instance = this
    }

    override fun onInterrupt() {
        Log.d(TAG, "Accessibility Service Interrupted")
    }
}