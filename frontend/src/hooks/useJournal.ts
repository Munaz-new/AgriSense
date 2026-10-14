import { useEffect,useState,useRef } from 'react';
import * as ImagePicker from 'expo-image-picker';
import { Platform } from 'react-native';
import { captureNativePhoto,pickedPhoto } from '../photoCapture';
import { captureBrowserPhoto } from '../browserCamera';
import { api,Observation,Plant,SoilCondition,ValidationResult,Health,Progression,ImageValidationError,PlantSuitabilityError,SuitabilityState } from '../api';
import { observationTime,retryId,captureObservation,scanBlockers } from '../recordState';
import type { Screen } from '../navigation/BottomNav';
import { draftStorageAvailable,writeDraft,readDraft,removeDraft } from '../draftStore';

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
  const [cropChoice,setCropChoice]=useState<'tomato'|'other'|'unknown'>('unknown');
  const [pendingPlant,setPendingPlant]=useState<{ id:string; name:string; crop:string|null }|null>(null);
  const [image,setImage]=useState<ImagePicker.ImagePickerAsset|null>(null);
  const [photoMessage,setPhotoMessage]=useState('');
  const cameraSession=useRef<AbortController|null>(null);
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
  const operation=useRef(false);
  const recoveredUri=useRef<string|null>(null);
  const [draftAvailable,setDraftAvailable]=useState(false);
  const [draftMessage,setDraftMessage]=useState('');
  const locked=busy||pendingId!==null||pendingPlant!==null;

  async function run(action: () => Promise<void>,releaseRejectedRequest=false) {
    // React state updates are asynchronous; guard rapid taps before the next render.
    if(operation.current) return;
    operation.current=true;
    setBusy(true); setError('');
    try { await action(); } catch(e) {
      const rejected=e instanceof ImageValidationError||(e instanceof PlantSuitabilityError&&e.code!=='plant_screening_unavailable');
      if(rejected&&releaseRejectedRequest) {
        // A definitive rejection saved nothing. Remove its old recovery identity
        // before allowing a fresh request, otherwise IndexedDB rejects that save.
        try { await removeDraft(); setDraftAvailable(false); }
        catch { setError('The photo was rejected, but its recovery copy could not be removed. Check history, then discard the draft before selecting another photo.'); return; }
      }
      if(e instanceof ImageValidationError) {
        setValidation(e.validation); setSuitability({ status: 'not_checked',message: '' });
        if(releaseRejectedRequest) { setPendingId(null); setPendingAnalysis(null); }
      }
      if(e instanceof PlantSuitabilityError) {
        setSuitability({ status: e.code==='non_plant_image'? 'rejected':e.code==='plant_content_uncertain'? 'inconclusive':'unavailable',message: e.message });
        if(releaseRejectedRequest&&e.code!=='plant_screening_unavailable') { setPendingId(null); setPendingAnalysis(null); }
      }
      setError(e instanceof Error? e.message:'Something went wrong. Please retry.');
    } finally { operation.current=false; setBusy(false); }
  }
  function forgetStoredDraft() {
    setDraftAvailable(false);
    void removeDraft().catch(() => { setDraftAvailable(true); setDraftMessage('The local recovery copy could not be removed. Retry discarding it; this does not delete saved observations.'); });
  }
  function clearDraft() {
    if(recoveredUri.current) { URL.revokeObjectURL(recoveredUri.current); recoveredUri.current=null; }
    forgetStoredDraft(); setDraftMessage(''); setPhotoMessage('');
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
  useEffect(() => {
    void run(async () => {
      try { setDraftAvailable((await readDraft())!==null); }
      catch(e) { setDraftAvailable(true); setDraftMessage(e instanceof Error?e.message:'Recovery storage is unavailable.'); }
      await loadPlants();
    });
    return () => {
      cameraSession.current?.abort();
      if(recoveredUri.current) URL.revokeObjectURL(recoveredUri.current);
    };
  },[]);
  function draftFields(id=pendingId,analysis=pendingAnalysis) {
    return { plantId: selected!.id,temperature,humidity,soilType,condition,observedAt,observedTimezone,trackingRef,notes,pendingId:id,pendingAnalysis:analysis };
  }
  async function keepDraft() {
    if(!selected||!image||locked) return;
    await run(async () => {
      if(await writeDraft(draftFields(),image)) { setDraftAvailable(true); setDraftMessage('Draft kept on this browser. It includes your photo and notes.'); }
    });
  }
  async function restoreDraft() {
    if(locked||image) return;
    await run(async () => {
      const draft=await readDraft();
      if(!draft) { setDraftAvailable(false); return; }
      const items=await api.plants();
      const plant=items.find(p => p.id===draft.plantId);
      if(!plant) throw new Error('The draft’s plant is unavailable on this backend. Its recovery copy has been retained.');
      const history=await api.observations(plant.id);
      setPlants(items); setSelected(plant); setRecords(previous => ({ ...previous,[plant.id]:history }));
      const saved=draft.pendingId? history.find(r => r.request_id===draft.pendingId):undefined;
      if(saved) { clearDraft(); setResult(saved); setScreen('result'); return; }
      recoveredUri.current=URL.createObjectURL(draft.photo);
      setImage({ uri:recoveredUri.current,width:0,height:0,fileName:draft.fileName,mimeType:draft.mimeType });
      setTemperature(draft.temperature); setHumidity(draft.humidity); setSoilType(draft.soilType); setCondition(draft.condition as SoilCondition|'');
      setObservedAt(draft.observedAt); setObservedTimezone(draft.observedTimezone); setTrackingRef(draft.trackingRef); setNotes(draft.notes);
      setPendingId(draft.pendingId); setPendingAnalysis(draft.pendingAnalysis);
      setValidation(null); setSuitability({ status:'not_checked',message:'' }); setScreen('scan');
      setDraftMessage('Draft restored. Check the photo again before saving. Any uncertain submission keeps its original request ID.');
    });
  }
  function navigate(next: Screen) {
    cameraSession.current?.abort();
    setError(''); setScreen(next);
  }
  async function openHistory(next: 'history'|'dashboard',plant=selected) {
    if(!plant) { navigate('plants'); return; }
    if(plant.id!==selected?.id&&!selectPlant(plant)) return;
    await run(async () => {
      const [items,comparison]=await Promise.all([api.observations(plant.id),api.progression(plant.id,plant.id===selected?.id? progressRef:'')]);
      setRecords(previous => ({ ...previous,[plant.id]: items }));
      setObservations(items); setProgress(comparison); setScreen(next);
    });
  }
  async function pick(camera: boolean) {
    if(locked||operation.current||!selected) return;
    if(draftAvailable&&!image) { setError('Restore or explicitly discard the local recovery copy before starting another photo.'); return; }
    await run(async () => {
      setPhotoMessage('');
      const session=new AbortController();
      if(camera) cameraSession.current=session;
      try {
        const picked=camera
          ? await (Platform.OS==='web'? captureBrowserPhoto(session.signal):captureNativePhoto())
          : await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'],allowsEditing: true,quality: 0.85 });
        if(session.signal.aborted) {
          if(camera&&Platform.OS==='web'&&!picked.canceled) URL.revokeObjectURL(picked.assets[0].uri);
          return;
        }
        const photo=pickedPhoto(picked);
        if(!photo) {
          setPhotoMessage(`${camera? 'Camera capture':'Photo selection'} canceled. ${image? 'Your previous photo is unchanged.':'No photo selected.'}`);
          return;
        }
        clearDraft(); setImage(photo); setImageRevision(value => value+1);
        if(camera&&Platform.OS==='web') recoveredUri.current=photo.uri;
        const captured=captureObservation();
        setObservedAt(captured.observedAt); setObservedTimezone(captured.observedTimezone);
        setPhotoMessage('Review your photo, then use it to check file and plant suitability. Nothing has been uploaded yet.');
      } finally {
        if(cameraSession.current===session) cameraSession.current=null;
      }
    });
  }
  function cancelPhoto() {
    if(locked||operation.current) return;
    clearDraft(); setPhotoMessage('Photo canceled. No saved observation was deleted.');
  }
  async function validateImage() {
    if(!image||busy) return;
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
        // Only a server screening response can describe suitability. Transport,
        // file and configuration errors leave suitability unknown, never rejected.
        if(!(e instanceof PlantSuitabilityError)) setSuitability({ status: 'not_checked',message: 'Photo checks did not complete. Resolve the error and retry; plant suitability has not been determined.' });
        throw e;
      }
    });
  }
  async function saveRecord(analyze=false) {
    if(pendingPlant) { setError('Finish the pending plant save in My Plants first.'); return; }
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
      // Persist exact bytes and request identity before transmission on supported browsers.
      await writeDraft(draftFields(id,analyze),image);
      setPendingId(id); setPendingAnalysis(analyze);
      const saved=await (analyze? api.scan:api.record)(selected.id,image,
        { temperature: temp,humidity: hum,soil_type: soilType.trim()||null,soil_condition: condition||null },
        { request_id: id,observed_at: timestamp,observed_timezone: observedTimezone,tracking_ref: trackingRef.trim()||null,notes: notes.trim()||null });
      setRecords(previous => ({ ...previous,[selected.id]: [...(previous[selected.id]||[]).filter(item => item.id!==saved.id),saved].sort((a,b) => (a.observed_at||a.created_at).localeCompare(b.observed_at||b.created_at)) }));
      clearDraft(); setResult(saved); setScreen('result');
    },true);
  }

  function selectPlant(plant: Plant) {
    if(plant.id===selected?.id) return true;
    if(locked||operation.current) return false;
    if(draftAvailable&&!image) { setError('Open Scan to restore or discard the local recovery copy first.'); return false; }
    setSelected(plant); setObservations([]); setProgress(null); setProgressRef(''); setResult(null);
    // A selected image and its server checks do not belong to a plant. Keep them
    // while clearing record-specific recovery data so a crop change does not
    // force a camera retake or discard a draft photo.
    forgetStoredDraft(); setDraftMessage('Photo kept. It will be saved under the newly selected plant.');
    setTemperature(''); setHumidity(''); setSoilType(''); setCondition('');
    setTrackingRef(''); setNotes(''); setPendingId(null); setPendingAnalysis(null);
    return true;
  }
  function startScan(plant=selected) {
    if(plant&&plant.id!==selected?.id&&!selectPlant(plant)) return;
    navigate('scan');
  }
  async function addPlant() {
    if(busy||pendingId!==null) return;
    if(draftAvailable&&!image) { setError('Open Scan to restore or discard the local recovery copy first.'); return; }
    await run(async () => {
      const crop=cropChoice==='tomato'? 'tomato':cropChoice==='other'? cropName.trim()||null:null;
      const request=pendingPlant||{ id:retryId(null),name:name.trim(),crop };
      if(!request.name) throw new Error('Enter a name for this plant.');
      setPendingPlant(request);
      const plant=await api.addPlant(request.name,request.crop,request.id);
      setPlants(previous => [plant,...previous.filter(item => item.id!==plant.id)]); setSelected(plant);
      setRecords(previous => ({ ...previous,[plant.id]: previous[plant.id]||[] }));
      setObservations([]); setProgress(null); setProgressRef(''); setResult(null); setName(''); setCropName(''); setCropChoice('unknown'); setPendingPlant(null);
    });
  }
  async function updatePlantCrop(plantId:string,crop:string|null):Promise<boolean> {
    if(busy||pendingId!==null||pendingPlant) return false;
    let succeeded=false;
    await run(async()=>{
      const updated=await api.updatePlantCrop(plantId,crop);
      setPlants(previous=>previous.map(item=>item.id===plantId?updated:item));
      setSelected(previous=>previous?.id===plantId?updated:previous);
      succeeded=true;
    });
    return succeeded;
  }
  function chooseCrop(choice:'tomato'|'other'|'unknown') {
    setCropChoice(choice);
    if(choice==='tomato') setCropName('');
    if(choice==='unknown') setCropName('');
  }
  return {
    analysisBlockers: [...(pendingPlant? ['Finish the pending plant save in My Plants first.']:[]),...scanBlockers({ busy,selected,image,validation,suitability,health,pendingAnalysis,temperature,humidity,soilType,condition },true)],
    recordBlockers: [...(pendingPlant? ['Finish the pending plant save in My Plants first.']:[]),...scanBlockers({ busy,selected,image,validation,suitability,health,pendingAnalysis,temperature,humidity,soilType,condition },false)],
    health,screen,plants,selected,records,observations,progress,progressRef,result,
    name,setName,cropName,setCropName,cropChoice,chooseCrop,image,imageRevision,photoMessage,cancelPhoto,validation,suitability,temperature,setTemperature,
    pendingPlant,discardPendingPlant: () => { if(!busy) setPendingPlant(null); },
    humidity,setHumidity,soilType,setSoilType,condition,setCondition,observedAt,observedTimezone,
    trackingRef,setTrackingRef,notes,setNotes,pendingId,pendingAnalysis,busy,error,locked,navigate,
    openHistory,pick,validateImage,saveRecord,clearDraft,selectPlant,startScan,addPlant,
    draftAvailable,draftMessage,draftRecoverySupported:draftStorageAvailable(),keepDraft,restoreDraft,forgetStoredDraft,
    updatePlantCrop,refresh: () => run(loadPlants),setProgressRef: (value: string) => { setProgressRef(value); setProgress(null); }
  };
}
export type Journal=ReturnType<typeof useJournal>;
