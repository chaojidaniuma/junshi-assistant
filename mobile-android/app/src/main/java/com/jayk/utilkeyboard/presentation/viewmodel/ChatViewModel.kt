package com.jayk.utilkeyboard.presentation.viewmodel

import androidx.lifecycle.LiveData
import androidx.lifecycle.MutableLiveData
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.jayk.utilkeyboard.data.ApiResult
import com.jayk.utilkeyboard.data.models.response.GenerateResponse
import com.jayk.utilkeyboard.data.repository.APIRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.launch
import javax.inject.Inject

@HiltViewModel
class ChatViewModel @Inject constructor(
    private val repository: APIRepository
) : ViewModel() {
    private val _result = MutableLiveData<GenerateResponse?>()
    val result: LiveData<GenerateResponse?> = _result

    private val _isLoading = MutableLiveData<Boolean>()
    val isLoading: LiveData<Boolean> = _isLoading

    private val _error = MutableLiveData<String?>()
    val error: LiveData<String?> = _error

    /** 生成军师建议。herMessage 是她最新消息。 */
    fun generate(herMessage: String, userId: String = "default") {
        viewModelScope.launch {
            _isLoading.value = true
            _error.value = null
            when (val r = repository.generate(herMessage, userId)) {
                is ApiResult.Success -> _result.postValue(r.data)
                is ApiResult.Error -> _error.postValue(r.message)
            }
            _isLoading.value = false
        }
    }
}
