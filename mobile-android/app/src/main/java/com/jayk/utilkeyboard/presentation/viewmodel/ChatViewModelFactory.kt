package com.jayk.utilkeyboard.presentation.viewmodel

import com.jayk.utilkeyboard.data.repository.APIRepository
import javax.inject.Inject

class ChatViewModelFactory @Inject constructor(
    private val repository: APIRepository
) {
    fun create(): ChatViewModel {
        return ChatViewModel(repository)
    }
}