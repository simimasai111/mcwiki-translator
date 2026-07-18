package com.mcwiki.translator

import android.Manifest
import android.annotation.SuppressLint
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.google.android.material.snackbar.Snackbar
import com.mcwiki.translator.databinding.ActivityMainBinding
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private val adapter = WikiAdapter { item ->
        // 点击条目打开原文链接
        if (item.link.isNotBlank()) {
            val intent = Intent(Intent.ACTION_VIEW, Uri.parse(item.link))
            startActivity(intent)
        }
    }

    private val updateReceiver = object : android.content.BroadcastReceiver() {
        override fun onReceive(context: android.content.Context?, intent: Intent?) {
            if (intent?.action == "com.mcwiki.translator.UPDATE") {
                loadData()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        setupRecyclerView()
        setupSwipeRefresh()
        setupControls()
        requestNotificationPermission()
        registerReceiver(updateReceiver, IntentFilter("com.mcwiki.translator.UPDATE"))

        // 恢复保存的服务器地址
        val prefs = getSharedPreferences("mcwiki", MODE_PRIVATE)
        binding.etServerUrl.setText(prefs.getString("server_url", "http://10.0.2.2:8765"))

        // 恢复服务状态
        val serviceEnabled = prefs.getBoolean("service_enabled", false)
        binding.switchService.isChecked = serviceEnabled

        loadData()
    }

    private fun setupRecyclerView() {
        binding.recyclerView.layoutManager = LinearLayoutManager(this)
        binding.recyclerView.adapter = adapter
    }

    private fun setupSwipeRefresh() {
        binding.swipeRefresh.setColorSchemeColors(0xFF5DADE2.toInt(), 0xFF48C9B0.toInt())
        binding.swipeRefresh.setOnRefreshListener {
            loadData()
        }
    }

    @SuppressLint("SetTextI18n")
    private fun setupControls() {
        binding.switchService.setOnCheckedChangeListener { _, isChecked ->
            val serverUrl = binding.etServerUrl.text.toString().trim()
            if (isChecked) {
                if (serverUrl.isBlank()) {
                    binding.switchService.isChecked = false
                    Snackbar.make(binding.root, "请输入服务器地址", Snackbar.LENGTH_SHORT).show()
                    return@setOnCheckedChangeListener
                }
                ApiClient.saveServerUrl(this, serverUrl)
                PollingService.start(this, serverUrl)
                getSharedPreferences("mcwiki", MODE_PRIVATE)
                    .edit().putBoolean("service_enabled", true).apply()
                Snackbar.make(binding.root, "后台监控已启动", Snackbar.LENGTH_SHORT).show()
            } else {
                PollingService.stop(this)
                getSharedPreferences("mcwiki", MODE_PRIVATE)
                    .edit().putBoolean("service_enabled", false).apply()
                Snackbar.make(binding.root, "后台监控已停止", Snackbar.LENGTH_SHORT).show()
            }
        }
    }

    private fun loadData() {
        binding.swipeRefresh.isRefreshing = true
        lifecycleScope.launch {
            try {
                val response = ApiClient.getFeed(limit = 100, context = this@MainActivity)
                binding.swipeRefresh.isRefreshing = false

                if (response.items.isEmpty()) {
                    binding.recyclerView.visibility = android.view.View.GONE
                    binding.tvEmpty.visibility = android.view.View.VISIBLE
                } else {
                    binding.recyclerView.visibility = android.view.View.VISIBLE
                    binding.tvEmpty.visibility = android.view.View.GONE
                    adapter.submitList(response.items)
                }
            } catch (e: Exception) {
                binding.swipeRefresh.isRefreshing = false
                binding.tvEmpty.text = "连接失败: ${e.message}\n请检查服务器地址"
                binding.recyclerView.visibility = android.view.View.GONE
                binding.tvEmpty.visibility = android.view.View.VISIBLE
            }
        }
    }

    private fun requestNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED
            ) {
                ActivityCompat.requestPermissions(
                    this, arrayOf(Manifest.permission.POST_NOTIFICATIONS), 100
                )
            }
        }
    }

    override fun onDestroy() {
        unregisterReceiver(updateReceiver)
        super.onDestroy()
    }
}