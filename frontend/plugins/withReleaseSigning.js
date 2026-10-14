const { withAppBuildGradle } = require('@expo/config-plugins');

/** Keep the generated release variant unsigned unless private signing material
 * is explicitly supplied through the local build environment. Never fall back
 * to Expo's debug keystore for a release APK.
 */
function withReleaseSigning(config) {
  return withAppBuildGradle(config, (mod) => {
    let contents = mod.modResults.contents;
    const environment = `def releaseStoreFile = System.getenv("AGRISENSE_ANDROID_KEYSTORE")
def releaseStorePassword = System.getenv("AGRISENSE_ANDROID_STORE_PASSWORD")
def releaseKeyAlias = System.getenv("AGRISENSE_ANDROID_KEY_ALIAS")
def releaseKeyPassword = System.getenv("AGRISENSE_ANDROID_KEY_PASSWORD")
def releaseSigningValues = [releaseStoreFile, releaseStorePassword, releaseKeyAlias, releaseKeyPassword]
def releaseSigningConfigured = releaseSigningValues.every { it != null && !it.isEmpty() }
if (releaseSigningValues.any { it != null && !it.isEmpty() } && !releaseSigningConfigured) {
    throw new GradleException("Provide all AGRISENSE_ANDROID_KEYSTORE, AGRISENSE_ANDROID_STORE_PASSWORD, AGRISENSE_ANDROID_KEY_ALIAS, and AGRISENSE_ANDROID_KEY_PASSWORD values for release signing.")
}

`;
    if (!contents.includes('def releaseSigningConfigured =')) {
      contents = contents.replace('android {', `${environment}android {`);
    }

    const signingAnchor = `        debug {
            storeFile file('debug.keystore')
            storePassword 'android'
            keyAlias 'androiddebugkey'
            keyPassword 'android'
        }
`;
    if (!contents.includes('releaseSigningConfigured) {\n                storeFile file(releaseStoreFile)')) {
      if (!contents.includes(signingAnchor)) {
        throw new Error('AgriSense Android release signing plugin could not find the generated debug signing block.');
      }
      contents = contents.replace(signingAnchor, `${signingAnchor}        release {
            if (releaseSigningConfigured) {
                storeFile file(releaseStoreFile)
                storePassword releaseStorePassword
                keyAlias releaseKeyAlias
                keyPassword releaseKeyPassword
            }
        }
`);
    }

    const debugFallback = `            // Caution! In production, you need to generate your own keystore file.
            // see https://reactnative.dev/docs/signed-apk-android.
            signingConfig signingConfigs.debug`;
    if (contents.includes(debugFallback)) {
      contents = contents.replace(debugFallback, `            if (releaseSigningConfigured) {
                signingConfig signingConfigs.release
            }`);
    } else if (!contents.includes('if (releaseSigningConfigured) {\n                signingConfig signingConfigs.release')) {
      throw new Error('AgriSense Android release signing plugin could not find the default debug release signature.');
    }

    mod.modResults.contents = contents;
    return mod;
  });
}

module.exports = withReleaseSigning;
