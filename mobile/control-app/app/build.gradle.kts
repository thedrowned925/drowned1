plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

val controlVersionCode = providers.gradleProperty("controlVersionCode").orNull?.toIntOrNull() ?: 1
val controlVersionName = providers.gradleProperty("controlVersionName").orNull ?: "1.0.0-dev"
val controlBuildSha = providers.gradleProperty("controlBuildSha").orNull ?: "dev"

android {
    namespace = "com.drowned.control"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.drowned.control"
        minSdk = 26
        targetSdk = 35
        versionCode = controlVersionCode
        versionName = controlVersionName
        buildConfigField("String", "CONTROL_BUILD_SHA", "\"$controlBuildSha\"")
    }

    val keystorePath = System.getenv("DROWNED_ANDROID_KEYSTORE")
    val releaseSigning = if (!keystorePath.isNullOrBlank()) {
        signingConfigs.create("controlRelease") {
            storeFile = file(keystorePath)
            storePassword = System.getenv("DROWNED_ANDROID_KEYSTORE_PASSWORD")
            keyAlias = System.getenv("DROWNED_ANDROID_KEY_ALIAS")
            keyPassword = System.getenv("DROWNED_ANDROID_KEY_PASSWORD")
        }
    } else {
        null
    }

    buildTypes {
        getByName("release") {
            isMinifyEnabled = false
            releaseSigning?.let { signingConfig = it }
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.10.0")
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.foundation:foundation")
    implementation("androidx.compose.material3:material3")
    implementation("io.coil-kt:coil-compose:2.7.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")

    debugImplementation("androidx.compose.ui:ui-tooling")
}
