import * as ImagePicker from 'expo-image-picker';

/** Native system camera only. Gallery selection never needs this permission. */
export async function captureNativePhoto(): Promise<ImagePicker.ImagePickerResult> {
  let permission;
  try {
    permission = await ImagePicker.getCameraPermissionsAsync();
    if (!permission.granted && permission.canAskAgain) {
      permission = await ImagePicker.requestCameraPermissionsAsync();
    }
  } catch {
    throw new Error('Camera permission could not be checked. Try again or choose a photo from the gallery.');
  }
  if (!permission.granted) {
    throw new Error(permission.canAskAgain
      ? 'Camera permission was denied. Tap Take Photo to try again, or choose from the gallery.'
      : 'Camera permission is disabled. Allow camera access in your phone settings for this app (Expo Go when using Expo Go), then try again. Gallery selection is still available.');
  }
  try {
    return await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'], allowsEditing: false, quality: 0.85,
      cameraType: ImagePicker.CameraType.back,
    });
  } catch {
    throw new Error('The camera could not open or return a photo. Check camera access in phone settings, close other camera apps and retry, or choose from the gallery.');
  }
}

/** Reject empty picker responses without clearing a previously usable photo. */
export function pickedPhoto(result: ImagePicker.ImagePickerResult): ImagePicker.ImagePickerAsset | null {
  if (result.canceled) return null;
  const asset = result.assets?.[0];
  if (!asset || typeof asset.uri !== 'string' || !asset.uri.trim()
    || asset.fileSize === 0 || (asset.width !== undefined && asset.width <= 0)
    || (asset.height !== undefined && asset.height <= 0)
    || asset.uri === 'data:,' || /^data:[^,]*,$/.test(asset.uri)) {
    throw new Error('No usable photo was returned. Please retake it or choose another image.');
  }
  return asset;
}
