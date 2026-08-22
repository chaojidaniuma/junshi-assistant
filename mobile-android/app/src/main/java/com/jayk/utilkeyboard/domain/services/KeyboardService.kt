package com.jayk.utilkeyboard.domain.services

import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.res.ColorStateList
import android.inputmethodservice.InputMethodService
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.HapticFeedbackConstants
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.widget.Button
import androidx.core.content.ContextCompat
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.recyclerview.widget.LinearLayoutManager
import com.jayk.utilkeyboard.Constants
import com.jayk.utilkeyboard.R
import com.jayk.utilkeyboard.data.models.response.GenerateResponse
import com.jayk.utilkeyboard.databinding.ChatSuggestionsLayoutBinding
import com.jayk.utilkeyboard.databinding.KeyboardLayoutBinding
import com.jayk.utilkeyboard.presentation.ui.SuggestionsAdapter
import com.jayk.utilkeyboard.presentation.viewmodel.ChatViewModel
import com.jayk.utilkeyboard.presentation.viewmodel.ChatViewModelFactory
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class KeyboardService(
) : InputMethodService(), ViewModelStoreOwner {

    private lateinit var suggestionsAdapter: SuggestionsAdapter

    @Inject
    lateinit var chatViewModelFactory: ChatViewModelFactory

    private lateinit var binding: KeyboardLayoutBinding
    private lateinit var chatBinding: ChatSuggestionsLayoutBinding
    private val serviceScope = CoroutineScope(Dispatchers.Main + Job())
    private val _viewModelStore by lazy { ViewModelStore() }
    private val chatViewModel: ChatViewModel by lazy {
        chatViewModelFactory.create()
    }
    private var isCapitalized = false
    private var isSymbolsMode = false
    private var isChatScreen = false

    override fun onWindowHidden() {
        super.onWindowHidden()
        isChatScreen = false
    }

    override fun onCreate() {
        super.onCreate()
        isChatScreen = false
        observeViewModel()
    }

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        isChatScreen = false
        setInputView(onCreateInputView())
    }

    /** 从剪贴板读取她复制的消息（无需无障碍权限）。 */
    private fun readClipboard(): String? {
        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as? ClipboardManager ?: return null
        val clip = cm.primaryClip ?: return null
        if (clip.itemCount == 0) return null
        return clip.getItemAt(0).coerceToText(this)?.toString()?.trim()?.takeIf { it.isNotEmpty() }
    }

    /** 生成军师建议：优先取剪贴板里复制的内容，否则用键盘顶部输入框。 */
    private fun generateSuggestions() {
        val source = readClipboard()
            ?: runCatching { chatBinding.herInput.text?.toString() }
                .getOrNull()?.trim()
        if (source.isNullOrBlank()) {
            chatBinding.apply {
                messageUnavailableText.visibility = View.VISIBLE
                messageUnavailableText.text = "复制她的消息，或在上方输入框粘贴"
            }
            return
        }
        chatBinding.apply {
            messageUnavailableText.visibility = View.GONE
        }
        val userId = Constants.userId(this@KeyboardService)
        chatViewModel.generate(source, userId)
    }

    override fun onDestroy() {
        super.onDestroy()
        isChatScreen = false
        serviceScope.cancel()
    }

    override val viewModelStore: ViewModelStore
        get() = _viewModelStore

    var backspaceHandler: Handler? = null
    val backspaceRunnable = object : Runnable {
        override fun run() {
            currentInputConnection?.sendKeyEvent(
                KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DEL)
            )
            backspaceHandler?.postDelayed(this, 50)
        }
    }
    private var spaceHandler: Handler? = null
    private var letterHandler: Handler? = null
    private var currentKey: String = ""

    private val keyRepeatRunnable = object : Runnable {
        override fun run() {
            currentInputConnection?.commitText(currentKey, 1)
            letterHandler?.postDelayed(this, 50)
        }
    }

    private val spaceRepeatRunnable = object : Runnable {
        override fun run() {
            currentInputConnection?.commitText(" ", 1)
            spaceHandler?.postDelayed(this, 50)
        }
    }


    override fun onCreateInputView(): View {
        println("on create input view called")
        binding = KeyboardLayoutBinding.inflate(layoutInflater)
        chatBinding = ChatSuggestionsLayoutBinding.inflate(layoutInflater)
        println("currently isChatScreen is $isChatScreen")

        setupButtons()
        setupRecyclerView()
        setupClickListeners()

        println(isCapitalized)

        fun commitText(text: String) {
            currentInputConnection?.commitText(text, 1)
        }

        fun performHapticFeedback(view: View) {
            view.performHapticFeedback(
                HapticFeedbackConstants.KEYBOARD_TAP,
            )
        }

        fun setupKeyWithRepeat(button: View, text: String) {
            button.setOnTouchListener { view, event ->
                view.background.setHotspot(event.x, event.y)

                when (event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        view.isPressed = true
                        performHapticFeedback(view)
                        currentKey = text
                        letterHandler = Handler(Looper.getMainLooper()).apply {
                            postDelayed(keyRepeatRunnable, 400) // Initial delay before repeat
                        }
                        currentInputConnection?.commitText(text, 1)
                        true
                    }
                    MotionEvent.ACTION_UP -> {
                        view.isPressed = false
                        letterHandler?.removeCallbacks(keyRepeatRunnable)
                        letterHandler = null
                        view.performClick()
                        true
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        view.isPressed = false
                        letterHandler?.removeCallbacks(keyRepeatRunnable)
                        letterHandler = null
                        true
                    }
                    else -> false
                }
            }
        }

        val letterButtons = mapOf(
            binding.btnA to Pair("a", "A"),
            binding.btnB to Pair("b", "B"),
            binding.btnC to Pair("c", "C"),
            binding.btnD to Pair("d", "D"),
            binding.btnE to Pair("e", "E"),
            binding.btnF to Pair("f", "F"),
            binding.btnG to Pair("g", "G"),
            binding.btnH to Pair("h", "H"),
            binding.btnI to Pair("i", "I"),
            binding.btnJ to Pair("j", "J"),
            binding.btnK to Pair("k", "K"),
            binding.btnL to Pair("l", "L"),
            binding.btnM to Pair("m", "M"),
            binding.btnN to Pair("n", "N"),
            binding.btnO to Pair("o", "O"),
            binding.btnP to Pair("p", "P"),
            binding.btnQ to Pair("q", "Q"),
            binding.btnR to Pair("r", "R"),
            binding.btnS to Pair("s", "S"),
            binding.btnT to Pair("t", "T"),
            binding.btnU to Pair("u", "U"),
            binding.btnV to Pair("v", "V"),
            binding.btnW to Pair("w", "W"),
            binding.btnX to Pair("x", "X"),
            binding.btnY to Pair("y", "Y"),
            binding.btnZ to Pair("z", "Z")
        )

        val numberButtons = mapOf(
            binding.btn0 to "0",
            binding.btn1 to "1",
            binding.btn2 to "2",
            binding.btn3 to "3",
            binding.btn4 to "4",
            binding.btn5 to "5",
            binding.btn6 to "6",
            binding.btn7 to "7",
            binding.btn8 to "8",
            binding.btn9 to "9"
        )

        val punctuationButtons = mapOf(
            binding.btnDot to ".",
            binding.btnComma to ","
        )

        val symbolButtons = mapOf(
            binding.btnStar to "*",
            binding.btnDQ to "\"",
            binding.btnSQ to "'",
            binding.btnColon to ":",
            binding.btnSemiColon to ";",
            binding.btnExclamation to "!",
            binding.btnQn to "?",
            binding.btnAt to "@",
            binding.btnHash to "#",
            binding.btnAnd to "&",
            binding.btnUnderscore to "_",
            binding.btnMinus to "-",
            binding.btnDollar to "$",
            binding.btnLeftBrace to "(",
            binding.btnRightBrace to ")",
            binding.btnPlus to "+",
            binding.btnSlash to "/"
        )


        fun updateButtonTexts() {
            if (isSymbolsMode) {
                symbolButtons.forEach { (button, symbol) ->
                    button.text = symbol
                }
            } else {
                letterButtons.forEach { (button, textPair) ->
                    button.text = if (isCapitalized) textPair.second else textPair.first
                }
            }
        }

        fun toggleSymbolsMode() {

            isSymbolsMode = !isSymbolsMode
            println(isSymbolsMode)
            if (isSymbolsMode) {
                binding.btnSymbols.setText("ABC")
            } else {
                binding.btnSymbols.setText("123")
            }
            binding.asdf.visibility = if (isSymbolsMode) View.GONE else View.VISIBLE
            binding.qwerty.visibility = if (isSymbolsMode) View.GONE else View.VISIBLE
            binding.SymbolsFirst.visibility = if (isSymbolsMode) View.VISIBLE else View.GONE
            binding.numbers.visibility = if (isSymbolsMode) View.VISIBLE else View.GONE
            binding.symbolsLast.visibility = if (isSymbolsMode) View.VISIBLE else View.GONE
            binding.zxcv.visibility = if (isSymbolsMode) View.GONE else View.VISIBLE
            updateButtonTexts()
        }

        letterButtons.forEach { (button, textPair) ->
            button.setOnTouchListener { view, event ->
                view.background.setHotspot(event.x, event.y)

                when (event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        view.isPressed = true
                        performHapticFeedback(view)
                        val textToCommit = if (isCapitalized) textPair.second else textPair.first
                        currentKey = textToCommit
                        letterHandler = Handler(Looper.getMainLooper()).apply {
                            postDelayed(keyRepeatRunnable, 400)
                        }
                        currentInputConnection?.commitText(textToCommit, 1)
                        true
                    }
                    MotionEvent.ACTION_UP -> {
                        view.isPressed = false  // Release pressed state
                        letterHandler?.removeCallbacks(keyRepeatRunnable)
                        letterHandler = null
                        view.performClick()
                        true
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        view.isPressed = false  // Release pressed state
                        letterHandler?.removeCallbacks(keyRepeatRunnable)
                        letterHandler = null
                        true
                    }
                    else -> false
                }
            }
        }

        // Apply to number buttons
        numberButtons.forEach { (button, text) ->
            setupKeyWithRepeat(button, text)
        }

        // Apply to symbol buttons
        symbolButtons.forEach { (button, text) ->
            setupKeyWithRepeat(button, text)
        }

        // Apply to punctuation buttons
        punctuationButtons.forEach { (button, text) ->
            setupKeyWithRepeat(button, text)
        }


        binding.btnSymbols.setOnClickListener { view ->
            performHapticFeedback(view)
            toggleSymbolsMode()
        }

        binding.btnBackSpace.apply {
            setOnClickListener {
                currentInputConnection?.sendKeyEvent(
                    KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DEL)
                )
            }

            setOnTouchListener { view, event ->
                when (event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        performHapticFeedback(view)
                        // Start continuous deletion after a delay
                        backspaceHandler = Handler(Looper.getMainLooper()).apply {
                            postDelayed(backspaceRunnable, 400)
                        }
                        true
                    }
                    MotionEvent.ACTION_UP -> {
                        backspaceHandler?.removeCallbacks(backspaceRunnable)
                        backspaceHandler = null
                        view.performClick()
                        true
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        backspaceHandler?.removeCallbacks(backspaceRunnable)
                        backspaceHandler = null
                        true
                    }
                    else -> false
                }
            }
        }

        binding.btnBackSpace2.apply {

            setOnClickListener {
                currentInputConnection?.sendKeyEvent(
                    KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_DEL)
                )
            }

            setOnTouchListener { view, event ->
                when (event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        performHapticFeedback(view)
                        // Start continuous deletion after a delay
                        backspaceHandler = Handler(Looper.getMainLooper()).apply {
                            postDelayed(backspaceRunnable, 400)
                        }
                        true
                    }
                    MotionEvent.ACTION_UP -> {
                        backspaceHandler?.removeCallbacks(backspaceRunnable)
                        backspaceHandler = null
                        view.performClick()
                        true
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        backspaceHandler?.removeCallbacks(backspaceRunnable)
                        backspaceHandler = null
                        true
                    }
                    else -> false
                }
            }
        }

        binding.btnCapitalize.setOnClickListener { view ->
            performHapticFeedback(view)
            isCapitalized = !isCapitalized
            updateButtonTexts()
            binding.btnCapitalize.backgroundTintList = ContextCompat.getColorStateList(
                baseContext,
                if (isCapitalized) R.color.primaryColor else R.color.greyColor
            )
        }

        binding.btnCapitalize2.setOnClickListener { view ->
            performHapticFeedback(view)
            isCapitalized = !isCapitalized
            updateButtonTexts()
            binding.btnCapitalize.backgroundTintList = ContextCompat.getColorStateList(
                baseContext,
                if (isCapitalized) R.color.primaryColor else R.color.greyColor
            )
        }

        //updateButtonTexts()

        binding.btnSpace.apply {
            setOnTouchListener { view, event ->
                view.background.setHotspot(event.x, event.y)

                when (event.action) {
                    MotionEvent.ACTION_DOWN -> {
                        view.isPressed = true
                        performHapticFeedback(view)

                        // Initial space press
                        currentInputConnection?.commitText(" ", 1)

                        // Start continuous spaces after delay
                        spaceHandler = Handler(Looper.getMainLooper()).apply {
                            postDelayed(spaceRepeatRunnable, 400)
                        }
                        true
                    }
                    MotionEvent.ACTION_UP -> {
                        view.isPressed = false
                        spaceHandler?.removeCallbacks(spaceRepeatRunnable)
                        spaceHandler = null
                        view.performClick()
                        true
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        view.isPressed = false
                        spaceHandler?.removeCallbacks(spaceRepeatRunnable)
                        spaceHandler = null
                        true
                    }
                    else -> false
                }
            }
        }

        binding.btnEnter.setOnClickListener { view ->
            performHapticFeedback(view)
            currentInputConnection?.sendKeyEvent(
                KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER)
            )
        }

        return if (isChatScreen) chatBinding.root else binding.root
    }

    private fun setupButtons() {
        // 六个情绪按钮全部触发「生成军师建议」；btnGoBack 返回 QWERTY
        val emotionButtons = listOf(
            chatBinding.btnHappy, chatBinding.btnSad, chatBinding.btnAngry,
            chatBinding.btnExcited, chatBinding.btnFlirty, chatBinding.btnFunny)
        emotionButtons.forEach { btn ->
            btn.setOnClickListener {
                updateButtonStates(it as Button, it.text.toString())
                showHerInput()
                generateSuggestions()
            }
        }

        chatBinding.btnGoBack.setOnClickListener {
            isChatScreen = false
            setInputView(onCreateInputView())
        }

        // 手动粘贴：点提示控件唤起输入框
        chatBinding.messageUnavailableText.setOnClickListener {
            chatBinding.herInput.visibility = View.VISIBLE
            chatBinding.herInput.requestFocus()
        }
    }

    private fun showHerInput() {
        // 没有剪贴板内容时，引导用户手动粘贴
        if (readClipboard().isNullOrBlank()) {
            chatBinding.messageUnavailableText.visibility = View.VISIBLE
            chatBinding.messageUnavailableText.text = "复制她的消息，或点下方输入框粘贴"
            chatBinding.herInput.visibility = View.VISIBLE
        }
    }

    private fun updateButtonStates(selectedButton: Button, mode: String) {
        chatBinding.apply {
            listOf(btnHappy, btnSad, btnAngry, btnFunny, btnExcited, btnFlirty).forEach {
                it.backgroundTintList = ColorStateList.valueOf(getColor(R.color.greyColor))
            }
        }
        selectedButton.backgroundTintList =
            ColorStateList.valueOf(getColor(R.color.primaryColor))
    }

    private fun setupRecyclerView() {
        suggestionsAdapter = SuggestionsAdapter { suggestion ->
            // Handle suggestion click
            getCurrentInputConnection()?.commitText(suggestion, 1)
        }

        chatBinding.suggestionsRecyclerView.apply {
            layoutManager = LinearLayoutManager(context)
            adapter = suggestionsAdapter
        }
    }

    private fun setupClickListeners() {
        binding.btnAI.setOnClickListener {
            isChatScreen = true
            setInputView(onCreateInputView())
            generateSuggestions()
        }
    }

    private fun observeViewModel() {
        chatViewModel.isLoading.observeForever { isLoading ->
            chatBinding.loadingIndicator.visibility =
                if (isLoading) View.VISIBLE else View.GONE
            if (!isLoading) chatBinding.suggestionsRecyclerView.visibility = View.VISIBLE
        }

        chatViewModel.result.observeForever { r ->
            renderResult(r)
        }

        chatViewModel.error.observeForever { e ->
            if (e != null) {
                chatBinding.loadingIndicator.visibility = View.GONE
                chatBinding.messageUnavailableText.visibility = View.VISIBLE
                chatBinding.messageUnavailableText.text = "生成失败：$e"
                chatBinding.signalText.visibility = View.GONE
                chatBinding.reasonText.visibility = View.GONE
            }
        }
    }

    private fun renderResult(r: GenerateResponse?) {
        if (r == null) return
        chatBinding.loadingIndicator.visibility = View.GONE
        chatBinding.messageUnavailableText.visibility = View.GONE
        chatBinding.suggestionsRecyclerView.visibility = View.VISIBLE
        suggestionsAdapter.submitList(r.replies.filter { it.isNotBlank() })

        chatBinding.apply {
            signalText.visibility = if (r.signal.isNullOrBlank()) View.GONE else View.VISIBLE
            signalText.text = r.signal ?: ""
            reasonText.visibility = if (r.reasoning.isNullOrBlank()) View.GONE else View.VISIBLE
            reasonText.text = r.reasoning ?: ""
        }
        // 没有剪贴板时清掉手动提示
        chatBinding.herInput.visibility = View.GONE
    }
}