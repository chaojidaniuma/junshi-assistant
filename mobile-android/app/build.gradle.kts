import java.util.Properties
import java.io.FileInputStream

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
    id("com.google.dagger.hilt.android")
    id("kotlin-kapt")
}

android {
    namespace = "com.jayk.utilkeyboard"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.jayk.utilkeyboard"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

//        val properties = Properties()
//
//        file("local.properties").takeIf { it.exists() }?.let {
//
//            FileInputStream(it).use { stream ->
//                properties.load(stream)
//                println("API_KEY loaded: ${properties.getProperty("API_KEY")}")
//            }
//        }
//        val apiKey = properties.getProperty("API_KEY") ?: "MISSING"
        buildConfigField("String", "API_KEY", "\"${project.findProperty("API_KEY")}\"")

//        val properties = Properties()
//        file("local.properties").takeIf { it.exists() }?.let {
//            FileInputStream(it).use { stream ->
//                properties.load(stream)
//            }
//        }
//        buildConfigField("String","API_KEY","\"${properties.getProperty("API_KEY")}\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = "1.8"
    }
    buildFeatures {
        viewBinding = true
        dataBinding = true
        buildConfig = true
    }
}

dependencies {

    // ViewModel
    implementation(libs.androidx.lifecycle.viewmodel.ktx)
    // LiveData
    implementation(libs.androidx.lifecycle.livedata.ktx)
    // Saved state module for ViewModel
    implementation(libs.androidx.lifecycle.viewmodel.savedstate)
    // Annotation processor
    kapt(libs.androidx.lifecycle.compiler)

    implementation(libs.kotlinx.coroutines.android)

    implementation("com.google.dagger:hilt-android:2.51.1") // Replace with the latest version
    kapt("com.google.dagger:hilt-android-compiler:2.51.1")

//    implementation(libs.dagger)
//    kapt(libs.dagger.compiler)

    implementation (libs.retrofit)

    implementation(libs.converter.gson)

    implementation(libs.logging.interceptor)

    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.1")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.6.1")
    implementation("androidx.lifecycle:lifecycle-common-java8:2.6.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.6.4")


    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.material)
    implementation(libs.androidx.activity)
    implementation(libs.androidx.constraintlayout)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
}