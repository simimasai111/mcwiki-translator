package com.mcwiki.translator

import android.view.LayoutInflater
import android.view.ViewGroup
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.mcwiki.translator.databinding.ItemWikiBinding

class WikiAdapter(
    private val onItemClick: (WikiItem) -> Unit
) : ListAdapter<WikiItem, WikiAdapter.ViewHolder>(DIFF_CALLBACK) {

    companion object {
        private val DIFF_CALLBACK = object : DiffUtil.ItemCallback<WikiItem>() {
            override fun areItemsTheSame(a: WikiItem, b: WikiItem) = a.hash == b.hash
            override fun areContentsTheSame(a: WikiItem, b: WikiItem) = a == b
        }
    }

    inner class ViewHolder(val binding: ItemWikiBinding) : RecyclerView.ViewHolder(binding.root)

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val binding = ItemWikiBinding.inflate(LayoutInflater.from(parent.context), parent, false)
        return ViewHolder(binding)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        val item = getItem(position)
        with(holder.binding) {
            // 有翻译显示翻译，否则显示原文
            tvTitleTranslated.text = item.titleTranslated?.ifBlank { null } ?: item.title
            tvTitleOriginal.text = item.title
            tvDescription.text = item.preview.ifBlank { "(无预览)" }
            tvMeta.text = buildString {
                append("作者: ${item.author}")
                if (item.pubDate.isNotBlank()) append("  |  ${formatDate(item.pubDate)}")
            }
            root.setOnClickListener { onItemClick(item) }
        }
    }

    private fun formatDate(dateStr: String): String {
        return try {
            val parts = dateStr.split(" ")
            if (parts.size >= 4) "${parts[1]} ${parts[2]} ${parts[3]}" else dateStr
        } catch (_: Exception) {
            dateStr
        }
    }
}