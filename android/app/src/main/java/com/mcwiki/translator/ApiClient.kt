package com.mcwiki.translator

import android.content.Context
import com.google.gson.Gson

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.net.HttpURLConnection
import java.net.URL

object ApiClient {

    private val gson = Gson()

    // 默认服务器地址，用户可在设置中修改
    var serverUrl: String = "http://10.0.2.2:8765"

    private fun loadServerUrl(context: Context) {
        val prefs = context.getSharedPreferences("mcwiki", Context.MODE_PRIVATE)
        serverUrl = prefs.getString("server_url", "http://10.0.2.2:8765") ?: "http://10.0.2.2:8765"
    }

    fun saveServerUrl(context: Context, url: String) {
        serverUrl = url
        context.getSharedPreferences("mcwiki", Context.MODE_PRIVATE)
            .edit().putString("server_url", url).apply()
    }

    private suspend fun fetchJson(path: String, context: Context): String = withContext(Dispatchers.IO) {
        loadServerUrl(context)
        val url = URL("${serverUrl.trimEnd('/')}$path")
        val conn = url.openConnection() as HttpURLConnection
        conn.connectTimeout = 10000
        conn.readTimeout = 15000
        conn.requestMethod = "GET"
        try {
            val code = conn.responseCode
            if (code == 200) {
                conn.inputStream.bufferedReader().readText()
            } else {
                throw Exception("HTTP $code")
            }
        } finally {
            conn.disconnect()
        }
    }

    suspend fun getFeed(since: String? = null, limit: Int = 50, context: Context): FeedResponse {
        var path = "/api/feed?limit=$limit"
        if (since != null) path += "&since=$since"
        val json = fetchJson(path, context)
        return gson.fromJson(json, FeedResponse::class.java)
    }

    suspend fun getStatus(context: Context): StatusResponse {
        val json = fetchJson("/api/status", context)
        return gson.fromJson(json, StatusResponse::class.java)
    }
}