package com.jayk.utilkeyboard

import android.content.Context
import android.content.SharedPreferences

object Constants {
    // AWS 测试服务器（文档 §6.1）
    // 正式环境改成 https://api.yourdomain.com/
    const val BASE_URL = "http://43.196.94.43:8000/"
    const val OBJECT_NAME = "对象"      // 关系对象名（键盘右上角可改）

    // 单例配置（对象名 / 用户ID），本地 SharedPreferences 持久化
    private const val PREFS = "junshi_prefs"
    fun prefs(ctx: Context): SharedPreferences =
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun objectName(ctx: Context): String =
        prefs(ctx).getString("object_name", OBJECT_NAME) ?: OBJECT_NAME

    fun userId(ctx: Context): String =
        prefs(ctx).getString("user_id", "default") ?: "default"

    fun setObject(ctx: Context, name: String) =
        prefs(ctx).edit().putString("object_name", name).apply()
}
