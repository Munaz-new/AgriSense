// Browser-only recovery. IndexedDB keeps the exact photo bytes with the request ID.
// Native recovery requires a durable file/storage adapter and is not claimed here.
import type { ImagePickerAsset } from 'expo-image-picker';
import { API_URL, imageBlob } from './api';

export type DraftFields = {
  plantId: string; temperature: string; humidity: string; soilType: string; condition: string;
  observedAt: string; observedTimezone: string; trackingRef: string; notes: string;
  pendingId: string | null; pendingAnalysis: boolean | null;
};
export type StoredDraft = DraftFields & { version: 1; photo: Blob; fileName: string; mimeType: string };
export const draftStorageAvailable = () => typeof indexedDB !== 'undefined';

export function validStoredDraft(value: unknown): value is StoredDraft {
  if (!value || typeof value !== 'object') return false;
  const d = value as StoredDraft;
  if (d.version !== 1 || !(d.photo instanceof Blob) || d.photo.size === 0 || d.photo.size > 10 * 1024 * 1024) return false;
  const limits: Record<string, number> = { plantId: 100, temperature: 100, humidity: 100, soilType: 100,
    condition: 10, observedAt: 100, observedTimezone: 100, trackingRef: 100, notes: 2000, fileName: 255, mimeType: 100 };
  for (const [key, limit] of Object.entries(limits)) {
    const item = (d as unknown as Record<string, unknown>)[key];
    if (typeof item !== 'string' || item.length > limit) return false;
  }
  return !!d.plantId && ['', 'Dry', 'Normal', 'Wet'].includes(d.condition) &&
    ((d.pendingId === null && d.pendingAnalysis === null) ||
      (typeof d.pendingId === 'string' && /^[A-Za-z0-9_-]{8,100}$/.test(d.pendingId) && typeof d.pendingAnalysis === 'boolean'));
}

async function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    let settled = false;
    const fail = (message: string) => { settled = true; clearTimeout(timer); reject(new Error(message)); };
    const timer = setTimeout(() => fail('Browser storage timed out. Close other AgriSense tabs and retry.'), 10000);
    const request = indexedDB.open('agrisense-drafts', 1);
    request.onupgradeneeded = () => request.result.createObjectStore('drafts');
    request.onsuccess = () => { clearTimeout(timer); if(settled) request.result.close(); else { settled = true; resolve(request.result); } };
    request.onerror = () => fail('Browser draft storage is unavailable. Check browser storage permissions.');
    request.onblocked = () => fail('Close other AgriSense tabs and try again.');
  });
}

// Order writes and deletes, including when a user discards immediately after saving.
let queue: Promise<unknown> = Promise.resolve();
function transaction<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const work = queue.catch(() => undefined).then(async () => {
    const db = await database();
    try {
      return await new Promise<T>((resolve, reject) => {
        const tx = db.transaction('drafts', mode);
        const timer = setTimeout(() => { tx.abort(); }, 10000);
        const request = action(tx.objectStore('drafts'));
        tx.oncomplete = () => { clearTimeout(timer); resolve(request.result); };
        tx.onerror = tx.onabort = () => { clearTimeout(timer); reject(new Error('Recovery storage failed or timed out. Close other tabs, restore any pending save, and check browser storage space.')); };
      });
    } finally { db.close(); }
  });
  queue = work;
  return work;
}

export async function writeDraft(fields: DraftFields, image: ImagePickerAsset): Promise<boolean> {
  if (!draftStorageAvailable()) return false;
  const photo = await imageBlob(image);
  const draft: StoredDraft = { ...fields, version: 1, photo, fileName: image.fileName || 'leaf.jpg', mimeType: image.mimeType || photo.type || 'image/jpeg' };
  if (!validStoredDraft(draft)) throw new Error('This draft cannot be stored. Use a photo up to 10 MB and check the field lengths.');
  await transaction('readwrite', store => {
    const previous = store.get(API_URL);
    previous.onsuccess = () => {
      // Never overwrite a different uncertain submission, including from another tab.
      if (previous.result?.pendingId && previous.result.pendingId !== fields.pendingId) store.transaction.abort();
      else store.put(draft, API_URL);
    };
    return previous;
  });
  return true;
}

export async function readDraft(): Promise<StoredDraft | null> {
  if (!draftStorageAvailable()) return null;
  const draft: unknown = await transaction('readonly', store => store.get(API_URL));
  if (draft === undefined) return null;
  if (!validStoredDraft(draft)) throw new Error('The saved draft is incompatible or damaged. Discard its local copy to start again.');
  return draft;
}

export async function removeDraft(): Promise<void> {
  if (draftStorageAvailable()) await transaction('readwrite', store => store.delete(API_URL));
}
