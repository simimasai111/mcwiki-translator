package com.mcwiki.translator

import android.annotation.SuppressLint
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.google.android.material.snackbar.Snackbar
import com.mcwiki.translator.databinding.ActivityDetailBinding
import kotlinx.coroutines.launch

class DetailActivity : AppCompatActivity() {

    private lateinit var binding: ActivityDetailBinding
    private var itemHash: String = ""
    private var detail: WikiItemDetail? = null
    private var showTranslated = false

    companion object {
        const val EXTRA_HASH = "item_hash"
        const val EXTRA_TITLE = "item_title"
    }

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityDetailBinding.inflate(layoutInflater)
        setContentView(binding.root)

        itemHash = intent.getStringExtra(EXTRA_HASH) ?: run { finish(); return }
        val title = intent.getStringExtra(EXTRA_TITLE) ?: ""

        binding.tvTitle.text = title
        binding.progressBar.visibility = View.VISIBLE

        // WebView 配置
        binding.webView.settings.javaScriptEnabled = true
        binding.webView.settings.builtInZoomControls = true
        binding.webView.settings.displayZoomControls = false
        binding.webView.settings.loadWithOverviewMode = true
        binding.webView.settings.useWideViewPort = true
        binding.webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
                url?.let { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it))) }
                return true
            }
        }

        // 翻译切换
        binding.btnTranslate.setOnClickListener {
            showTranslated = !showTranslated
            binding.btnTranslate.text = if (showTranslated) "显示原文" else "翻译中文"
            renderContent()
            if (showTranslated && detail?.descriptionTranslated == null) {
                requestTranslation()
            }
        }

        // 打开原文链接
        binding.btnOpenLink.setOnClickListener {
            detail?.link?.let { link ->
                if (link.isNotBlank()) startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(link)))
            }
        }

        loadDetail()
    }

    private fun loadDetail() {
        lifecycleScope.launch {
            try {
                detail = ApiClient.getItem(itemHash, this@DetailActivity)
                binding.progressBar.visibility = View.GONE

                // 标题用翻译版（如果有）
                detail?.titleTranslated?.let { binding.tvTitle.text = it }

                // 元信息
                binding.tvMeta.text = buildString {
                    append("作者: ${detail?.author ?: ""}")
                    if (!detail?.pubDate.isNullOrBlank()) append("  |  ${detail?.pubDate}")
                }
                binding.tvMeta.visibility = View.VISIBLE

                renderContent()

                // 按钮区
                binding.btnTranslate.visibility = View.VISIBLE
                binding.btnOpenLink.visibility = View.VISIBLE
            } catch (e: Exception) {
                binding.progressBar.visibility = View.GONE
                Snackbar.make(binding.root, "加载失败: ${e.message}", Snackbar.LENGTH_LONG).show()
            }
        }
    }

    private fun renderContent() {
        val d = detail ?: return
        val html = if (showTranslated && d.descriptionTranslated != null) {
            wrapHtml(d.descriptionTranslated!!)
        } else {
            wrapHtml(d.descriptionHtml.ifBlank { d.descriptionPreview })
        }
        binding.webView.loadDataWithBaseURL(null, html, "text/html", "UTF-8", null)
    }

    private fun wrapHtml(content: String): String {
        // 包装 HTML，加上深色主题样式，让 diff 表格更易读
        return """
        <html><head><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=3">
        <style>
        body {
            font-family: -apple-system, sans-serif;
            background: #1a1a2e;
            color: #e0e0e0;
            padding: 12px;
            font-size: 14px;
            line-height: 1.5;
        }
        p { margin: 8px 0; color: #ccc; }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 10px 0;
            background: #16213e;
            border-radius: 6px;
            overflow: hidden;
        }
        td { padding: 6px 8px; border: 1px solid #2a3a5c; vertical-align: top; font-size: 13px; }
        .diff-marker { width: 20px; text-align: center; background: #0f1a2e; }
        .diff-lineno { background: #0a1525; color: #888; font-size: 11px; }
        .diff-title td { background: #0a1525; color: #888; text-align: center; font-size: 11px; }
        ins { color: #48c9b0; text-decoration: none; font-weight: bold; }
        del { color: #e74c3c; text-decoration: line-through; }
        a { color: #5dade2; }
        div { margin: 4px 0; }
        </style>
        </head><body>$content</body></html>
        """.trimIndent()
    }

    private fun requestTranslation() {
        binding.progressBar.visibility = View.VISIBLE
        lifecycleScope.launch {
            try {
                // 先翻译标题
                if (detail?.titleTranslated == null) {
                    val titleRes = ApiClient.translateItem(itemHash, "title", this@DetailActivity)
                    detail = detail?.copy(titleTranslated = titleRes.translated)
                    titleRes.translated.let { binding.tvTitle.text = it }
                }
                // 再翻译描述
                val descRes = ApiClient.translateItem(itemHash, "description", this@DetailActivity)
                detail = detail?.copy(descriptionTranslated = descRes.translated)
                renderContent()
            } catch (e: Exception) {
                Snackbar.make(binding.root, "翻译失败: ${e.message}", Snackbar.LENGTH_LONG).show()
                showTranslated = false
                binding.btnTranslate.text = "翻译中文"
                renderContent()
            } finally {
                binding.progressBar.visibility = View.GONE
            }
        }
    }
}