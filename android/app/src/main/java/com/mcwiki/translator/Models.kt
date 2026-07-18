package com.mcwiki.translator

data class WikiItem(
    val hash: String = "",
    val titleOriginal: String = "",
    val titleTranslated: String = "",
    val descriptionOriginal: String = "",
    val descriptionTranslated: String = "",
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

data class StatusResponse(
    val status: String = "",
    val totalCached: Int = 0,
    val latestFetch: String? = null,
    val rssSource: String = ""
)