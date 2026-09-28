import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as ImagePicker from 'expo-image-picker';
import { api, API_URL, Observation, Plant, SoilCondition, ValidationResult, Health, Progression, ImageValidationError } from './src/api';

import { recordLabels, progressionLabel, observationTime, retryId } from './src/recordState';

type Screen = 'home' | 'scan' | 'result' | 'history' | 'dashboard';
const date = (value: string) => new Date(value).toLocaleString();

function Button({ title, onPress, disabled = false, secondary = false }: {
  title: string; onPress: () => void; disabled?: boolean; secondary?: boolean;
}) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled}
    onPress={onPress} style={[s.button, secondary && s.secondary, disabled && s.disabled]}>
    <Text style={[s.buttonText, secondary && s.secondaryText]}>{title}</Text>
  </Pressable>;
}
function Field({ label, value, setValue, numeric = false, disabled = false }: {
  label: string; value: string; setValue: (text: string) => void; numeric?: boolean; disabled?: boolean;
}) {
  return <View style={s.field}><Text style={s.label}>{label}</Text>
    <TextInput accessibilityLabel={label} style={s.input} editable={!disabled} value={value} onChangeText={setValue}
      keyboardType={numeric ? 'numbers-and-punctuation' : 'default'} maxLength={100} />
  </View>;
}
function Result({ observation }: { observation: Observation }) {
  const labels = recordLabels(observation);
  return <View style={s.card}>
    <Image accessibilityLabel="Recorded plant photo" source={{ uri: `${API_URL}${observation.image_path}` }} style={s.photo} />
    <Text style={s.title}>{labels.disease}</Text>
    <Text style={s.body}>{labels.severity}</Text>
    <Text style={s.body}>{labels.confidence}</Text>
    <Text style={s.notice}>{labels.notice}</Text>
    <Text style={s.muted}>{observation.observed_at ? `Observed ${date(observation.observed_at)}` : 'Observation time not supplied'}</Text>
    <Text style={s.muted}>Saved {date(observation.created_at)}</Text>
    {observation.tracking_ref && <Text style={s.body}>Leaf / site: {observation.tracking_ref}</Text>}
    {observation.notes && <Text style={s.body}>{observation.notes}</Text>}
    {observation.duplicate_of && <Text style={s.notice}>This exact image was recorded previously for this plant. It is not new progression evidence.</Text>}
    <Text style={s.body}>{observation.temperature}°C · {observation.humidity}% humidity</Text>
    <Text style={s.body}>{observation.soil_type} soil · {observation.soil_condition}</Text>
    <Text style={s.muted}>Environment is user-entered context only.</Text>
    {observation.predictor && <Text style={s.muted}>Analysis source: {observation.predictor}</Text>}
    {observation.checkpoint_id && <Text style={s.muted}>Model artifact: {observation.checkpoint_id}</Text>}
  </View>;
}

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [screen, setScreen] = useState<Screen>('home');
  const [plants, setPlants] = useState<Plant[]>([]);
  const [selected, setSelected] = useState<Plant | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [progress, setProgress] = useState<Progression | null>(null);
  const [progressRef, setProgressRef] = useState('');
  const [result, setResult] = useState<Observation | null>(null);
  const [name, setName] = useState('');
  const [cropName, setCropName] = useState('');
  const [image, setImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [temperature, setTemperature] = useState('');
  const [humidity, setHumidity] = useState('');
  const [soilType, setSoilType] = useState('');
  const [condition, setCondition] = useState<SoilCondition>('Normal');
  const [observedAt, setObservedAt] = useState('');
  const [trackingRef, setTrackingRef] = useState('');
  const [notes, setNotes] = useState('');
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const locked = busy || pendingId !== null;

  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch (e) {
      if (e instanceof ImageValidationError) setValidation(e.validation);
      setError(e instanceof Error ? e.message : 'Something went wrong. Please retry.');
    } finally { setBusy(false); }
  }
  function clearDraft() {
    setImage(null); setValidation(null); setPendingId(null);
    setTemperature(''); setHumidity(''); setSoilType(''); setCondition('Normal');
    setObservedAt(''); setTrackingRef(''); setNotes('');
  }
  async function loadPlants() {
    const [status, items] = await Promise.all([api.health(), api.plants()]);
    setHealth(status); setPlants(items);
  }
  useEffect(() => { void run(loadPlants); }, []);
  function navigate(next: Screen) { setError(''); setScreen(next); }
  async function openHistory(next: 'history' | 'dashboard') {
    if (!selected) return;
    await run(async () => {
      const [items, comparison] = await Promise.all([api.observations(selected.id), api.progression(selected.id, progressRef)]);
      setObservations(items); setProgress(comparison); setScreen(next);
    });
  }
  async function pick(camera: boolean) {
    await run(async () => {
      if (camera) {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) throw new Error('Camera permission is needed. You can also select a photo.');
      }
      const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], allowsEditing: true, quality: 0.85 };
      const picked = camera ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
      if (!picked.canceled) { clearDraft(); setImage(picked.assets[0]); }
    });
  }
  async function validateImage() {
    if (!image) return;
    setValidation(null);
    await run(async () => { setValidation(await api.validateImage(image)); });
  }
  async function saveRecord() {
    if (!selected || !image || !validation?.is_valid) return;
    await run(async () => {
      const temp = Number(temperature); const hum = Number(humidity);
      if (!temperature.trim() || !Number.isFinite(temp) || temp < -50 || temp > 70) throw new Error('Enter a temperature between -50 and 70°C.');
      if (!humidity.trim() || !Number.isFinite(hum) || hum < 0 || hum > 100) throw new Error('Enter humidity between 0 and 100%.');
      if (!soilType.trim()) throw new Error('Enter the soil type.');
      const timestamp = observationTime(observedAt);
      const id = retryId(pendingId);
      setPendingId(id);
      const saved = await api.record(selected.id, image,
        { temperature: temp, humidity: hum, soil_type: soilType.trim(), soil_condition: condition },
        { request_id: id, observed_at: timestamp, tracking_ref: trackingRef.trim() || null, notes: notes.trim() || null });
      setResult(saved); clearDraft(); setScreen('result');
    });
  }

  return <SafeAreaProvider><SafeAreaView style={s.safe}>
    <StatusBar style="dark" />
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      <View style={s.header}><Text style={s.brand}>AgriSense</Text><Text style={s.muted}>Your plants, one observation at a time.</Text></View>
      <Text style={s.notice}>{health ? health.analysis_message : 'Connecting to observation service…'}</Text>
      {screen !== 'home' && <Button title="← Home / select plant" secondary disabled={locked} onPress={() => navigate('home')} />}
      {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
      {busy && <ActivityIndicator accessibilityLabel="Loading" color="#19734a" />}
      {pendingId && screen !== 'scan' && <Button title="Return to pending record" disabled={busy} onPress={() => navigate('scan')} />}

      {screen === 'home' && <>
        <Text style={s.title}>My plants</Text>
        <Text style={s.body}>Give each physical plant its own record, then add photos over time.</Text>
        <View style={s.card}>
          <Field disabled={busy} label="Plant name / identifier" value={name} setValue={setName} />
          <Field disabled={busy} label="Crop name (optional, user identified)" value={cropName} setValue={setCropName} />
          <Button title="Add plant" disabled={busy || !name.trim()} onPress={() => void run(async () => {
            const plant = await api.addPlant(name.trim(), cropName.trim() || null);
            setPlants(previous => [plant, ...previous]); setSelected(plant); setObservations([]); setProgress(null); setProgressRef(''); setResult(null); clearDraft(); setName(''); setCropName('');
          })} />
        </View>
        <Button title="Refresh plants" secondary disabled={busy} onPress={() => void run(loadPlants)} />
        {!plants.length && <Text style={s.muted}>No plants yet. Add your first plant above.</Text>}
        {plants.map(plant => <Pressable accessibilityRole="button" accessibilityState={{ selected: selected?.id === plant.id, disabled: busy }}
          disabled={busy} key={plant.id} style={[s.card, selected?.id === plant.id && s.selected]}
          onPress={() => { setSelected(plant); setObservations([]); setProgress(null); setProgressRef(''); setResult(null); clearDraft(); }}>
          <Text style={s.label}>{selected?.id === plant.id ? '✓ ' : ''}{plant.name}</Text>
          <Text style={s.muted}>{plant.crop_name || 'Crop not recorded'} · Added {date(plant.created_at)}</Text>
        </Pressable>)}
        {selected && <View style={s.card}><Text style={s.title}>{selected.name}</Text>
          <Button title="New observation" disabled={busy || !health?.capabilities.record_only} onPress={() => navigate('scan')} />
          <Button title="Plant history" secondary disabled={busy} onPress={() => void openHistory('history')} />
          <Button title="Health dashboard" secondary disabled={busy} onPress={() => void openHistory('dashboard')} />
        </View>}
      </>}

      {screen === 'scan' && <>
        <Text style={s.title}>New observation · {selected?.name}</Text>
        <View style={s.card}>
          {image ? <Image accessibilityLabel="Selected plant photo" source={{ uri: image.uri }} style={s.photo} /> : <Text style={s.placeholder}>Choose a clear plant photo</Text>}
          <Button title="Capture plant photo" disabled={locked} onPress={() => void pick(true)} />
          <Button title="Select from photos" secondary disabled={locked} onPress={() => void pick(false)} />
          <Text style={s.muted}>JPEG, PNG or WebP · maximum 10 MB · at least 224 × 224 pixels · at most 8192 pixels per side and 24 MP</Text>
          <Text style={s.notice}>Technical validation only. Plant content and crop identity are not verified. No disease, confidence or severity result is generated when you save.</Text>
          <Button title="Validate image" disabled={busy || !image} onPress={() => void validateImage()} />
          {validation && <Text style={validation.is_valid ? s.notice : s.error}>{validation.message}</Text>}
          {validation?.is_valid && <>
            <Field disabled={locked} label="Temperature (°C)" numeric value={temperature} setValue={setTemperature} />
            <Field disabled={locked} label="Humidity (%)" numeric value={humidity} setValue={setHumidity} />
            <Field disabled={locked} label="Soil type" value={soilType} setValue={setSoilType} />
            <Text style={s.label}>Soil condition</Text>
            <View style={s.row}>{(['Dry', 'Normal', 'Wet'] as SoilCondition[]).map(value =>
              <Button key={value} title={value} secondary={condition !== value} disabled={locked} onPress={() => setCondition(value)} />)}</View>
            <Field disabled={locked} label="Observed at (optional ISO time with timezone)" value={observedAt} setValue={setObservedAt} />
            <Text style={s.muted}>Use YYYY-MM-DDTHH:mm:ss+05:30. Leave blank if unknown; save time is recorded separately.</Text>
            <Field disabled={locked} label="Leaf / site reference (optional)" value={trackingRef} setValue={setTrackingRef} />
            <Text style={s.muted}>Reuse a reference only for the same leaf or observation site. A reference alone does not establish comparable measurements.</Text>
            <Field disabled={locked} label="Notes (optional)" value={notes} setValue={setNotes} />
            <Button title={pendingId ? 'Retry the same save' : 'Save observation without analysis'} disabled={busy} onPress={() => void saveRecord()} />
          </>}
          {pendingId && <>
            <Text style={s.notice}>The save may already have completed. Retry uses the same request ID. Keep this form open while checking history; drafts are not retained after an app restart.</Text>
            <Button title="Check saved history" secondary disabled={busy} onPress={() => void openHistory('history')} />
            <Button title="Discard this form after checking history" secondary disabled={busy} onPress={clearDraft} />
            <Text style={s.muted}>Discarding the form does not delete any saved record.</Text>
          </>}
        </View>
      </>}
      {screen === 'result' && result && <>
        <Text style={s.title}>Observation saved · {selected?.name}</Text><Result observation={result} />
        <Button title="View plant history" disabled={busy} onPress={() => void openHistory('history')} />
        <Button title="Health dashboard" secondary disabled={busy} onPress={() => void openHistory('dashboard')} />
      </>}
      {screen === 'history' && <>
        <Text style={s.title}>{selected?.name} · History</Text>
        <Text style={s.muted}>Newest first by observation time; save time is used when observation time is unknown.</Text>
        <Button title="Refresh history" secondary disabled={busy} onPress={() => void openHistory('history')} />
        <Button title="Health dashboard" disabled={busy} onPress={() => void openHistory('dashboard')} />
        {!observations.length && <Text style={s.muted}>No observations yet.</Text>}
        {[...observations].reverse().map(observation => <Result key={observation.id} observation={observation} />)}
      </>}
      {screen === 'dashboard' && <>
        <Text style={s.title}>{selected?.name} · Health dashboard</Text>
        <View style={s.card}>
          <Text style={s.label}>Recorded history</Text>
          <Text style={s.body}>{observations.length} observation{observations.length === 1 ? '' : 's'}</Text>
          <Text style={s.muted}>Oldest → newest. These are records, not an inferred health score.</Text>
          {observations.map((observation, index) => <View key={observation.id} style={s.field}>
            <Text style={s.body}>#{index + 1} · {date(observation.observed_at || observation.created_at)}{!observation.observed_at ? ' (save time)' : ''}</Text>
            <Text style={s.muted}>{recordLabels(observation).severity}</Text>
            {observation.is_mock && <Text style={s.notice}>Synthetic historical record • excluded from real progression</Text>}
          </View>)}
        </View>
        <View style={s.card}>
          <Text style={s.label}>Severity comparison</Text>
          <Field disabled={busy} label="Leaf / site reference to compare" value={progressRef} setValue={value => { setProgressRef(value); setProgress(null); }} />
          <Button title="Refresh comparison" secondary disabled={busy} onPress={() => void openHistory('dashboard')} />
          {progress && <>
            <Text style={s.title}>{progressionLabel(progress)}</Text>
            <Text style={s.body}>{progress.message}</Text>
            {progress.previous_observed_at && progress.latest_observed_at && <Text style={s.muted}>{date(progress.previous_observed_at)} → {date(progress.latest_observed_at)}</Text>}
          </>}
          <Text style={s.notice}>Severity measurement and a validated comparison policy are unavailable. Confidence and disease labels are never converted into severity or recovery claims.</Text>
        </View>
        <Button title="Full observation history" disabled={busy} onPress={() => void openHistory('history')} />
      </>}
    </ScrollView>
  </SafeAreaView></SafeAreaProvider>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#f3f8f4' },
  page: { padding: 22, gap: 14, maxWidth: 760, width: '100%', alignSelf: 'center', paddingBottom: 48 },
  header: { paddingVertical: 14, gap: 4 }, brand: { fontSize: 34, fontWeight: '800', color: '#155c3c' },
  title: { fontSize: 23, fontWeight: '700', color: '#173f2d' },
  body: { fontSize: 16, color: '#284d3a', lineHeight: 24 }, muted: { fontSize: 13, color: '#587263', lineHeight: 20 },
  label: { fontSize: 16, fontWeight: '600', color: '#214b35' },
  notice: { backgroundColor: '#e4f0d8', color: '#36531e', padding: 12, borderRadius: 10, fontSize: 12, lineHeight: 18 },
  card: { backgroundColor: '#fff', borderRadius: 18, padding: 18, gap: 12, borderWidth: 1, borderColor: '#dce9df' },
  selected: { borderColor: '#19734a', borderWidth: 2, backgroundColor: '#ecf7ef' },
  field: { gap: 7, marginVertical: 4 }, input: { backgroundColor: '#fff', borderColor: '#a6bdae', borderWidth: 1, padding: 13, borderRadius: 10, color: '#173f2d', fontSize: 16 },
  button: { backgroundColor: '#19734a', paddingVertical: 14, paddingHorizontal: 18, borderRadius: 11, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 15 }, secondary: { backgroundColor: '#e5f1e9' }, secondaryText: { color: '#155c3c' },
  disabled: { opacity: 0.5 }, row: { flexDirection: 'row', gap: 8, flexWrap: 'wrap' },
  photo: { width: '100%', height: 240, borderRadius: 12, backgroundColor: '#e5f1e9', resizeMode: 'cover' },
  placeholder: { textAlign: 'center', paddingVertical: 60, backgroundColor: '#edf5ee', color: '#587263', borderRadius: 12 },
  metric: { fontSize: 28, color: '#19734a', fontWeight: '700' },
  error: { color: '#992f26', backgroundColor: '#ffebe7', borderRadius: 10, padding: 14, lineHeight: 22 },
  track: { height: 16, borderRadius: 8, backgroundColor: '#e5f1e9', overflow: 'hidden' },
  bar: { height: 16, backgroundColor: '#2d8b59', borderRadius: 8 },
});
