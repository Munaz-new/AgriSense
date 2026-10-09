import { useEffect,useState,useRef } from 'react';
import * as ImagePicker from 'expo-image-picker';
import { api,Observation,Plant,SoilCondition,ValidationResult,Health,Progression,ImageValidationError,PlantSuitabilityError,SuitabilityState } from '../api';
import { observationTime,retryId,captureObservation,scanBlockers } from '../recordState';
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
  const [suitability,setSuitability]=useState<SuitabilityState>({ status: 'not_checked',message: '' });
  const [imageRevision,setImageRevision]=useState(0);
  const draftVersion=useRef(0);
  const [temperature,setTemperature]=useState('');
  const [humidity,setHumidity]=useState('');
  const [soilType,setSoilType]=useState('');
  const [condition,setCondition]=useState<SoilCondition|''>('');
  const [observedAt,setObservedAt]=useState('');
  const [observedTimezone,setObservedTimezone]=useState('');
  const [trackingRef,setTrackingRef]=useState('');
  const [notes,setNotes]=useState('');
  const [pendingId,setPendingId]=useState<string|null>(null);
  const [pendingAnalysis,setPendingAnalysis]=useState<boolean|null>(null);
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState('');
  const locked=busy||pendingId!==null;

  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch(e) {
      if(e instanceof ImageValidationError) {
        setValidation(e.validation); setSuitability({ status: 'not_checked',message: '' });
        setPendingId(null); setPendingAnalysis(null);
      }
      if(e instanceof PlantSuitabilityError) {
        setSuitability({ status: e.code==='non_plant_image'? 'rejected':e.code==='plant_content_uncertain'? 'inconclusive':'unavailable',message: e.message });
        if(e.code!=='plant_screening_unavailable') { setPendingId(null); setPendingAnalysis(null); }
      }
      setError(e instanceof Error? e.message:'Something went wrong. Please retry.');
    } finally { setBusy(false); }
  }
  function clearDraft() {
    draftVersion.current+=1;
    setResult(null); setError(''); setSuitability({ status: 'not_checked',message: '' });
    setImage(null); setValidation(null); setPendingId(null); setPendingAnalysis(null);
    setTemperature(''); setHumidity(''); setSoilType(''); setCondition('');
    setObservedAt(''); setObservedTimezone(''); setTrackingRef(''); setNotes('');
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
    if(locked) return;
    await run(async () => {
      if(camera) {
        const permission=await ImagePicker.requestCameraPermissionsAsync();
        if(!permission.granted) throw new Error('Camera permission is needed. You can also select a photo.');
      }
      const options: ImagePicker.ImagePickerOptions={ mediaTypes: ['images'],allowsEditing: true,quality: 0.85 };
      const picked=camera? await ImagePicker.launchCameraAsync(options):await ImagePicker.launchImageLibraryAsync(options);
      if(!picked.canceled) {
        clearDraft(); setImage(picked.assets[0]); setImageRevision(value => value+1);
        const captured=captureObservation();
        setObservedAt(captured.observedAt); setObservedTimezone(captured.observedTimezone);
      }
    });
  }
  async function validateImage() {
    if(!image||locked) return;
    const version=draftVersion.current;
    setValidation(null);
    setSuitability({ status: 'not_checked',message: '' });
    await run(async () => {
      try {
        const checked=await api.validateImage(image);
        if(version!==draftVersion.current) return;
        setValidation(checked);
        if(!checked.is_valid) return;
        setSuitability({ status: 'checking',message: 'Checking plant suitability…' });
        const screened=await api.checkSuitability(image);
        if(version!==draftVersion.current) return;
        if(screened.outcome!=='plant') throw new Error('Plant suitability was not accepted. Try another photo.');
        setSuitability({ status: 'accepted',message: screened.message });
      } catch(e) {
        if(version!==draftVersion.current) return;
        if(!(e instanceof ImageValidationError)) setSuitability({ status: 'unavailable',message: e instanceof Error? e.message:'Suitability check failed.' });
        throw e;
      }
    });
  }
  async function saveRecord(analyze=false) {
    const reasons=scanBlockers({ busy,selected,image,validation,suitability,health,pendingAnalysis,temperature,humidity,soilType,condition },analyze);
    if(reasons.length) { setError(reasons.join(' ')); return; }
    if(!selected||!image) return;
    await run(async () => {
      if(pendingAnalysis!==null&&pendingAnalysis!==analyze) throw new Error('Retry the same action or discard the draft after checking history.');
      if(analyze&&(!health?.capabilities.tomato_analysis||selected.crop_name?.trim().toLowerCase()!=='tomato')) throw new Error('Tomato analysis is unavailable for this plant. Save without analysis instead.');
      const temp=temperature.trim()? Number(temperature):null;
      const hum=humidity.trim()? Number(humidity):null;
      const timestamp=observationTime(observedAt);
      const id=retryId(pendingId);
      setPendingId(id); setPendingAnalysis(analyze);
      const saved=await (analyze? api.scan:api.record)(selected.id,image,
        { temperature: temp,humidity: hum,soil_type: soilType.trim()||null,soil_condition: condition||null },
        { request_id: id,observed_at: timestamp,observed_timezone: observedTimezone,tracking_ref: trackingRef.trim()||null,notes: notes.trim()||null });
      setRecords(previous => ({ ...previous,[selected.id]: [...(previous[selected.id]||[]).filter(item => item.id!==saved.id),saved].sort((a,b) => (a.observed_at||a.created_at).localeCompare(b.observed_at||b.created_at)) }));
      clearDraft(); setResult(saved); setScreen('result');
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
    analysisBlockers: scanBlockers({ busy,selected,image,validation,suitability,health,pendingAnalysis,temperature,humidity,soilType,condition },true),
    recordBlockers: scanBlockers({ busy,selected,image,validation,suitability,health,pendingAnalysis,temperature,humidity,soilType,condition },false),
    health,screen,plants,selected,records,observations,progress,progressRef,result,
    name,setName,cropName,setCropName,image,imageRevision,validation,suitability,temperature,setTemperature,
    humidity,setHumidity,soilType,setSoilType,condition,setCondition,observedAt,observedTimezone,
    trackingRef,setTrackingRef,notes,setNotes,pendingId,pendingAnalysis,busy,error,locked,navigate,
    openHistory,pick,validateImage,saveRecord,clearDraft,selectPlant,startScan,addPlant,
    refresh: () => run(loadPlants),setProgressRef: (value: string) => { setProgressRef(value); setProgress(null); }
  };
}
export type Journal=ReturnType<typeof useJournal>;
