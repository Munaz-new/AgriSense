import { useEffect,useState } from 'react';
import * as ImagePicker from 'expo-image-picker';
import { api,Observation,Plant,SoilCondition,ValidationResult,Health,Progression,ImageValidationError } from '../api';
import { observationTime,retryId } from '../recordState';
import type { Screen } from '../navigation/BottomNav';

export function useJournal() {
  const [health,setHealth]=useState<Health|null>(null);
  const [screen,setScreen]=useState<Screen>('home');
  const [records,setRecords]=useState<Record<string,Observation[]>>({});
  const [plants,setPlants]=useState<Plant[]>([]);
  const [selected,setSelected]=useState<Plant|null>(null);
  const [observations,setObservations]=useState<Observation[]>([]);
  const [progress,setProgress]=useState<Progression|null>(null);
  const [progressRef,setProgressRef]=useState('');
  const [result,setResult]=useState<Observation|null>(null);
  const [name,setName]=useState('');
  const [cropName,setCropName]=useState('');
  const [image,setImage]=useState<ImagePicker.ImagePickerAsset|null>(null);
  const [validation,setValidation]=useState<ValidationResult|null>(null);
  const [temperature,setTemperature]=useState('');
  const [humidity,setHumidity]=useState('');
  const [soilType,setSoilType]=useState('');
  const [condition,setCondition]=useState<SoilCondition>('Normal');
  const [observedAt,setObservedAt]=useState('');
  const [trackingRef,setTrackingRef]=useState('');
  const [notes,setNotes]=useState('');
  const [pendingId,setPendingId]=useState<string|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const locked=busy||pendingId!==null;

  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch(e) {
      if(e instanceof ImageValidationError) setValidation(e.validation);
      setError(e instanceof Error? e.message:'Something went wrong. Please retry.');
    } finally { setBusy(false); }
  }
  function clearDraft() {
    setImage(null); setValidation(null); setPendingId(null);
    setTemperature(''); setHumidity(''); setSoilType(''); setCondition('Normal');
    setObservedAt(''); setTrackingRef(''); setNotes('');
  }
  async function loadPlants() {
    try {
      const [status,items]=await Promise.all([api.health(),api.plants()]);
      setHealth(status); setPlants(items);
      setSelected(previous => previous? items.find(item => item.id===previous.id)||null:items[0]||null);
      const histories=await Promise.all(items.map(async plant => [plant.id,await api.observations(plant.id)] as const));
      setRecords(Object.fromEntries(histories));
    } catch(e) {
      setHealth(null);
      throw e;
    }
  }
  useEffect(() => { void run(loadPlants); },[]);
  function navigate(next: Screen) { setError(''); setScreen(next); }
  async function openHistory(next: 'history'|'dashboard',plant=selected) {
    if(!plant) { navigate('plants'); return; }
    await run(async () => {
      const [items,comparison]=await Promise.all([api.observations(plant.id),api.progression(plant.id,plant.id===selected?.id? progressRef:'')]);
      if(plant.id!==selected?.id) selectPlant(plant);
      setRecords(previous => ({ ...previous,[plant.id]: items }));
      setObservations(items); setProgress(comparison); setScreen(next);
    });
  }
  async function pick(camera: boolean) {
    await run(async () => {
      if(camera) {
        const permission=await ImagePicker.requestCameraPermissionsAsync();
        if(!permission.granted) throw new Error('Camera permission is needed. You can also select a photo.');
      }
      const options: ImagePicker.ImagePickerOptions={ mediaTypes: ['images'],allowsEditing: true,quality: 0.85 };
      const picked=camera? await ImagePicker.launchCameraAsync(options):await ImagePicker.launchImageLibraryAsync(options);
      if(!picked.canceled) { clearDraft(); setImage(picked.assets[0]); }
    });
  }
  async function validateImage() {
    if(!image) return;
    setValidation(null);
    await run(async () => { setValidation(await api.validateImage(image)); });
  }
  async function saveRecord() {
    if(!selected||!image||!validation?.is_valid) return;
    await run(async () => {
      const temp=Number(temperature); const hum=Number(humidity);
      if(!temperature.trim()||!Number.isFinite(temp)||temp<-50||temp>70) throw new Error('Enter a temperature between -50 and 70°C.');
      if(!humidity.trim()||!Number.isFinite(hum)||hum<0||hum>100) throw new Error('Enter humidity between 0 and 100%.');
      if(!soilType.trim()) throw new Error('Enter the soil type.');
      const timestamp=observationTime(observedAt);
      const id=retryId(pendingId);
      setPendingId(id);
      const saved=await api.record(selected.id,image,
        { temperature: temp,humidity: hum,soil_type: soilType.trim(),soil_condition: condition },
        { request_id: id,observed_at: timestamp,tracking_ref: trackingRef.trim()||null,notes: notes.trim()||null });
      setRecords(previous => ({ ...previous,[selected.id]: [...(previous[selected.id]||[]).filter(item => item.id!==saved.id),saved].sort((a,b) => (a.observed_at||a.created_at).localeCompare(b.observed_at||b.created_at)) }));
      setResult(saved); clearDraft(); setScreen('result');
    });
  }

  function selectPlant(plant: Plant) {
    if(locked||plant.id===selected?.id) return;
    setSelected(plant); setObservations([]); setProgress(null); setProgressRef(''); setResult(null); clearDraft();
  }
  function startScan(plant=selected) {
    if(plant&&plant.id!==selected?.id) selectPlant(plant);
    navigate('scan');
  }
  async function addPlant() {
    await run(async () => {
      const plant=await api.addPlant(name.trim(),cropName.trim()||null);
      setPlants(previous => [plant,...previous]); setSelected(plant);
      setRecords(previous => ({ ...previous,[plant.id]: [] }));
      setObservations([]); setProgress(null); setProgressRef(''); setResult(null); clearDraft(); setName(''); setCropName('');
    });
  }
  return {
    health,screen,plants,selected,records,observations,progress,progressRef,result,
    name,setName,cropName,setCropName,image,validation,temperature,setTemperature,
    humidity,setHumidity,soilType,setSoilType,condition,setCondition,observedAt,setObservedAt,
    trackingRef,setTrackingRef,notes,setNotes,pendingId,busy,error,locked,navigate,
    openHistory,pick,validateImage,saveRecord,clearDraft,selectPlant,startScan,addPlant,
    refresh: () => run(loadPlants),setProgressRef: (value: string) => { setProgressRef(value); setProgress(null); }
  };
}
export type Journal=ReturnType<typeof useJournal>;
