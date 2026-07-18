# Add project specific ProGuard rules here.
-keep class com.mcwiki.translator.** { *; }
-keepattributes *Annotation*
-keep class com.google.gson.** { *; }
-keep class com.mcwiki.translator.WikiItem { *; }
-keep class com.mcwiki.translator.FeedResponse { *; }
-keep class com.mcwiki.translator.StatusResponse { *; }