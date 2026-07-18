package com.mcwiki.translator

import android.app.*
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import kotlinx.coroutines.*

class PollingService : Service() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var pollJob: Job? = null

    companion object {
        const val CHANNEL_ID = "mcwiki_updates"
        const val NOTIFICATION_ID = 1001
        const val EXTRA_SERVER_URL = "server_url"

        fun start(context: Context, serverUrl: String = "") {
            val intent = Intent(context, PollingService::class.java)
            if (serverUrl.isNotBlank()) intent.putExtra(EXTRA_SERVER_URL, serverUrl)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, PollingService::class.java))
        }
    }

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        startForegroundNotification()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        intent?.getStringExtra(EXTRA_SERVER_URL)?.let {
            if (it.isNotBlank()) ApiClient.serverUrl = it
        }
        startPolling()
        return START_STICKY
    }

    private fun startPolling() {
        pollJob?.cancel()
        pollJob = serviceScope.launch {
            while (isActive) {
                try {
                    checkForUpdates()
                } catch (e: Exception) {
                    e.printStackTrace()
                }
                delay(60_000) // 每分钟检查一次
            }
        }
    }

    private suspend fun checkForUpdates() {
        val prefs = getSharedPreferences("mcwiki", MODE_PRIVATE)
        val lastFetchTime = prefs.getString("last_fetch_time", "") ?: ""

        val response = ApiClient.getFeed(
            since = if (lastFetchTime.isBlank()) null else lastFetchTime,
            limit = 30,
            context = this
        )

        if (response.items.isNotEmpty()) {
            // 更新最后拉取时间
            prefs.edit().putString("last_fetch_time", response.serverTime).apply()

            // 发送通知
            showUpdateNotification(response.items)

            // 广播给 Activity 刷新
            sendBroadcast(Intent("com.mcwiki.translator.UPDATE"))
        }
    }

    private fun showUpdateNotification(items: List<WikiItem>) {
        val summary = if (items.size == 1) {
            items[0].titleTranslated
        } else {
            "${items.size} 条新翻译: ${items.firstOrNull()?.titleTranslated} 等"
        }

        val inboxStyle = NotificationCompat.InboxStyle()
            .setBigContentTitle("Minecraft Wiki 更新")
            .setSummaryText(summary)

        items.take(5).forEach { item ->
            inboxStyle.addLine("• ${item.titleTranslated}")
        }
        if (items.size > 5) {
            inboxStyle.addLine("...还有 ${items.size - 5} 条")
        }

        val intent = Intent(this, MainActivity::class.java)
        val pendingIntent = PendingIntent.getActivity(
            this, 0, intent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("⛏ Minecraft Wiki 翻译更新")
            .setContentText(summary)
            .setStyle(inboxStyle)
            .setContentIntent(pendingIntent)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_DEFAULT)
            .build()

        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        notificationManager.notify(NOTIFICATION_ID + System.currentTimeMillis().toInt() % 1000, notification)
    }

    private fun startForegroundNotification() {
        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setContentTitle("Wiki 翻译监控运行中")
            .setContentText("正在后台监控 Minecraft Wiki 更新")
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()

        startForeground(NOTIFICATION_ID, notification)
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Wiki 翻译更新",
                NotificationManager.IMPORTANCE_DEFAULT
            ).apply {
                description = "接收 Minecraft Wiki 翻译推送通知"
            }
            val manager = getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(channel)
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        pollJob?.cancel()
        serviceScope.cancel()
        super.onDestroy()
    }
}