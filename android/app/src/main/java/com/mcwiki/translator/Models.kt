package com.mcwiki.translator

data class WikiItem(
    val hash: String = "",
    val title: String = "",
    val titleTranslated: String? = null,
    val preview: String = "",
    val author: String = "",
    val pubDate: String = "",
    val fetchTime: String = "",
    val link: String = ""
)

data class WikiItemDetail(
    val hash: String = "",
    val title: String = "",
    val titleTranslated: String? = null,
    val descriptionHtml: String = "",
    val descriptionPreview: String = "",
    val descriptionTranslated: String? = null,
    val link: String = "",
    val author: String = "",
    val pubDate: String = "",
    val fetchTime: String = ""
)

data class FeedResponse(
    val items: List<WikiItem> = emptyList(),
    val total: Int = 0,
    val serverTime: String = ""
)

data class TranslateResponse(
    val translated: String = ""
)

data class StatusResponse(
    val status: String = "",
    val totalCached: Int = 0,
    val latestFetch: String? = null,
    val rssSource: String = ""
)