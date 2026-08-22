package com.jayk.utilkeyboard.presentation.ui

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.jayk.utilkeyboard.databinding.ChatCardLayoutBinding

// Adapter for suggestions
class SuggestionsAdapter(
    private val onItemClick: (String) -> Unit
) : ListAdapter<String, SuggestionsAdapter.ViewHolder>(DiffCallback()) {

    class ViewHolder(private val binding: ChatCardLayoutBinding) :
        RecyclerView.ViewHolder(binding.root) {

        fun bind(suggestion: String, onItemClick: (String) -> Unit) {
            binding.tvSuggestion.text = suggestion
            binding.root.setOnClickListener { onItemClick(suggestion) }
        }

        companion object {
            fun from(parent: ViewGroup): ViewHolder {
                val layoutInflater = LayoutInflater.from(parent.context)
                val binding = ChatCardLayoutBinding.inflate(
                    layoutInflater, parent, false
                )
                return ViewHolder(binding)
            }
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        return ViewHolder.from(parent)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position), onItemClick)
    }

    class DiffCallback : DiffUtil.ItemCallback<String>() {
        override fun areItemsTheSame(oldItem: String, newItem: String) =
            oldItem == newItem
        override fun areContentsTheSame(oldItem: String, newItem: String) =
            oldItem == newItem
    }
}