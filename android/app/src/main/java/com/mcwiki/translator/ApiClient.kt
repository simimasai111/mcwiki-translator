package com.mcwiki.translator

import android.content.Context
import com.google.gson.Gson
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

object ApiClient {

    private val gson = Gson()
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
            if (conn.responseCode == 200) conn.inputStream.bufferedReader().readText()
            else throw Exception("HTTP ${conn.responseCode}")
        } finally {
            conn.disconnect()
        }
    }

    private suspend fun postJson(path: String, body: String, context: Context): String = withContext(Dispatchers.IO) {
        loadServerUrl(context)
        val url = URL("${serverUrl.trimEnd('/')}$path")
        val conn = url.openConnection() as HttpURLConnection
        conn.connectTimeout = 15000
        conn.readTimeout = 30000
        conn.requestMethod = "POST"
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        conn.doOutput = true
        try {
            OutputStreamWriter(conn.outputStream, "UTF-8").use { it.write(body) }
            if (conn.responseCode == 200) conn.inputStream.bufferedReader().readText()
            else throw Exception("HTTP ${conn.responseCode}")
        } finally {
            conn.disconnect()
        }
    }

    suspend fun getFeed(since: String? = null, limit: Int = 50, context: Context): FeedResponse {
        var path = "/api/feed?limit=$limit"
        if (since != null) path += "&since=${URLEncoder.encode(since, "UTF-8")}"
        return gson.fromJson(fetchJson(path, context), FeedResponse::class.java)
    }

    suspend fun getItem(hash: String, context: Context): WikiItemDetail {
        val json = fetchJson("/api/item?hash=${URLEncoder.encode(hash, "UTF-8")}", context)
        return gson.fromJson(json, WikiItemDetail::class.java)
    }

    suspend fun translateItem(hash: String, field: String, context: Context): TranslateResponse {
        val body = """{"hash":"$hash","field":"$field"}"""
        return gson.fromJson(postJson("/api/translate", body, context), TranslateResponse::class.java)
    }

    suspend fun translateText(text: String, context: Context): TranslateResponse {
        val escaped = gson.toJson(text)
        val body = """{"text":$escaped}"""
        return gson.fromJson(postJson("/api/translate", body, context), TranslateResponse::class.java)
    }

    suspend fun getStatus(context: Context): StatusResponse {
        return gson.fromJson(fetchJson("/api/status", context), StatusResponse::class.java)
    }
}