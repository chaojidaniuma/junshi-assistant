package com.jayk.utilkeyboard.presentation.di

import android.content.Context
import android.view.accessibility.AccessibilityManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton
import android.content.Context.ACCESSIBILITY_SERVICE
import com.jayk.utilkeyboard.domain.repositories.AccessibilityRepositoryImpl
import com.jayk.utilkeyboard.domain.repositories.AccessibilityRepository

@Module()
@InstallIn(SingletonComponent::class)
object AccessibilityModule {

    @Provides
    @Singleton
    fun provideAccessibilityManager(@ApplicationContext context: Context) : AccessibilityManager{
        return context.getSystemService(ACCESSIBILITY_SERVICE) as AccessibilityManager
    }

    @Provides
    @Singleton
    fun provideAccessibilityRepository(@ApplicationContext context: Context,accessibilityManager: AccessibilityManager) : AccessibilityRepository {
        return AccessibilityRepositoryImpl(context,accessibilityManager)
    }

}