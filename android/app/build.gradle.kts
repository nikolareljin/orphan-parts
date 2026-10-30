import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

// The version is the repository's VERSION file; the code is derived from it so every release
// has a higher one (x.y.z -> x*10000 + y*100 + z).
val versionText = rootProject.file("../VERSION").readText().trim()
val versionParts = versionText.split(".").map { it.toInt() }

// A release keystore is given through the environment or android/keystore.properties (ignored);
// without one the release build is signed with the debug key, which installs but is not for a
// store.
val keystoreProps = Properties().apply {
    val f = rootProject.file("keystore.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}
fun prop(name: String): String =
    listOf(System.getenv(name), keystoreProps.getProperty(name)).firstOrNull { !it.isNullOrBlank() }.orEmpty()
val releaseKeystore = prop("KEYSTORE_PATH")

android {
    namespace = "com.orphanparts.lens"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.orphanparts.lens"
        minSdk = 26
        targetSdk = 35
        versionCode = versionParts[0] * 10000 + versionParts[1] * 100 + versionParts[2]
        versionName = versionText
    }

    signingConfigs {
        create("release") {
            if (releaseKeystore.isNotBlank()) {
                storeFile = file(releaseKeystore)
                storePassword = prop("KEYSTORE_PASSWORD")
                keyAlias = prop("KEY_ALIAS")
                keyPassword = prop("KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (releaseKeystore.isNotBlank()) signingConfigs.getByName("release") else signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")
    implementation(composeBom)
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.exifinterface:exifinterface:1.3.7")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.9.0")
    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20240303")
}
