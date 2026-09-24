import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as ImagePicker from 'expo-image-picker';
import { api, API_URL, Observation, Plant, SoilCondition, ValidationResult, Prediction, ImageValidationError } from './src/api';

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
  return <View style={s.card}>
    <Image accessibilityLabel="Scanned leaf" source={{ uri: `${API_URL}${observation.image_path}` }} style={s.photo} />
    <Text style={s.title}>{observation.disease}</Text>
    <Text style={s.metric}>{observation.severity === null ? 'Severity not estimated' : `${observation.severity}% severity`}</Text>
    <Text style={s.body}>{observation.confidence}% confidence</Text>
    <Text style={s.notice}>{observation.is_mock ? 'DEVELOPMENT MOCK • Synthetic demo result, not a diagnosis.' : observation.predictor}</Text>
    <Text style={s.muted}>{date(observation.created_at)}</Text>
    <Text style={s.body}>{observation.temperature}°C · {observation.humidity}% humidity</Text>
    <Text style={s.body}>{observation.soil_type} soil · {observation.soil_condition}</Text>
    <Text style={s.muted}>Environment is recorded as context only.</Text>
  </View>;
}

export default function App() {
  const [mockMode, setMockMode] = useState<boolean | null>(null);
  const [screen, setScreen] = useState<Screen>('home');
  const [plants, setPlants] = useState<Plant[]>([]);
  const [selected, setSelected] = useState<Plant | null>(null);
  const [observations, setObservations] = useState<Observation[]>([]);
  const [result, setResult] = useState<Observation | null>(null);
  const [name, setName] = useState('');
  const [image, setImage] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [validation, setValidation] = useState<ValidationResult | null>(null);
  const [prediction, setPrediction] = useState<Prediction | null>(null);
  const [temperature, setTemperature] = useState('');
  const [humidity, setHumidity] = useState('');
  const [soilType, setSoilType] = useState('');
  const [condition, setCondition] = useState<SoilCondition>('Normal');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function run(action: () => Promise<void>) {
    setBusy(true); setError('');
    try { await action(); } catch (e) {
      if (e instanceof ImageValidationError) { setValidation(e.validation); setPrediction(null); }
      setError(e instanceof Error ? e.message : 'Something went wrong. Please retry.');
    }
    finally { setBusy(false); }
  }
  async function loadPlants() {
    const [health, items] = await Promise.all([api.health(), api.plants()]);
    setMockMode(health.is_mock); setPlants(items);
  }
  useEffect(() => { void run(loadPlants); }, []);
  function navigate(next: Screen) { setError(''); setScreen(next); }
  async function openHistory(next: 'history' | 'dashboard') {
    if (!selected) return;
    await run(async () => { setObservations(await api.observations(selected.id)); setScreen(next); });
  }
  async function pick(camera: boolean) {
    await run(async () => {
      if (camera) {
        const permission = await ImagePicker.requestCameraPermissionsAsync();
        if (!permission.granted) throw new Error('Camera permission is needed to capture a leaf. You can also select a photo.');
      }
      const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], allowsEditing: true, quality: 0.85 };
      const picked = camera ? await ImagePicker.launchCameraAsync(options) : await ImagePicker.launchImageLibraryAsync(options);
      if (!picked.canceled) {
        setImage(picked.assets[0]); setValidation(null); setPrediction(null);
        setTemperature(''); setHumidity(''); setSoilType(''); setCondition('Normal');
      }
    });
  }
  async function validateImage() {
    if (!image) return;
    setValidation(null); setPrediction(null);
    await run(async () => { setValidation(await api.validateImage(image)); });
  }
  function environmentIsValid(): boolean {
    if (!selected || !image || !validation?.is_valid) { setError('Select an image and pass technical validation first.'); return false; }
    const temp = Number(temperature); const hum = Number(humidity);
    if (!temperature.trim() || !Number.isFinite(temp) || temp < -50 || temp > 70) { setError('Enter a temperature between -50 and 70°C.'); return false; }
    if (!humidity.trim() || !Number.isFinite(hum) || hum < 0 || hum > 100) { setError('Enter humidity between 0 and 100%.'); return false; }
    if (!soilType.trim()) { setError('Enter the soil type.'); return false; }
    return true;
  }
  async function analyze() {
    if (!environmentIsValid() || !image) return;
    setPrediction(null);
    await run(async () => { setPrediction(await api.predict(image)); });
  }
  async function saveScan() {
    if (!environmentIsValid() || !selected || !image || !prediction) return;
    await run(async () => {
      const saved = await api.scan(selected.id, image, { temperature: Number(temperature), humidity: Number(humidity), soil_type: soilType.trim(), soil_condition: condition });
      setResult(saved); setImage(null); setValidation(null); setPrediction(null); setTemperature(''); setHumidity(''); setSoilType(''); setCondition('Normal'); setScreen('result');
    });
  }
  const latest = observations.at(-1);
  const first = observations[0];
  const change = latest?.severity != null && first?.severity != null ? latest.severity - first.severity : null;

  return <SafeAreaProvider><SafeAreaView style={s.safe}>
    <StatusBar style="dark" />
    <ScrollView contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
      <View style={s.header}><Text style={s.brand}>AgriSense</Text><Text style={s.muted}>Your plants, one observation at a time.</Text></View>
      <Text style={s.notice}>{mockMode === null ? 'PHASE 2A · Connecting to prediction service…' : mockMode ? 'PHASE 2A · DEVELOPMENT-ONLY MOCK PREDICTIONS' : 'PHASE 2A · Image prediction service'}</Text>
      {screen !== 'home' && <Button title="← Home / select plant" secondary disabled={busy} onPress={() => navigate('home')} />}
      {error ? <Text accessibilityRole="alert" style={s.error}>{error}</Text> : null}
      {busy && <ActivityIndicator accessibilityLabel="Loading" color="#19734a" />}

      {screen === 'home' && <>
        <Text style={s.title}>My plants</Text>
        <Text style={s.body}>Add a crop, select it, then record a leaf scan.</Text>
        <View style={s.card}>
          <Field label="Plant / crop name" value={name} setValue={setName} />
          <Button title="Add plant" disabled={busy || !name.trim()} onPress={() => void run(async () => {
            const plant = await api.addPlant(name.trim()); setPlants(previous => [plant, ...previous]); setSelected(plant); setObservations([]); setResult(null); setImage(null); setValidation(null); setPrediction(null); setName('');
          })} />
        </View>
        <Button title="Refresh plants" secondary disabled={busy} onPress={() => void run(loadPlants)} />
        {!plants.length && <Text style={s.muted}>No plants yet. Add your first plant above.</Text>}
        {plants.map(plant => <Pressable accessibilityRole="button" accessibilityState={{ selected: selected?.id === plant.id, disabled: busy }}
          disabled={busy} key={plant.id} style={[s.card, selected?.id === plant.id && s.selected]}
          onPress={() => { setSelected(plant); setObservations([]); setResult(null); setImage(null); setValidation(null); setPrediction(null); }}>
          <Text style={s.label}>{selected?.id === plant.id ? '✓ ' : ''}{plant.name}</Text>
          <Text style={s.muted}>Added {date(plant.created_at)}</Text>
        </Pressable>)}
        {selected && <View style={s.card}><Text style={s.title}>{selected.name}</Text>
          <Button title="New scan" disabled={busy} onPress={() => navigate('scan')} />
          <Button title="Plant history" secondary disabled={busy} onPress={() => void openHistory('history')} />
          <Button title="Health dashboard" secondary disabled={busy} onPress={() => void openHistory('dashboard')} />
        </View>}
      </>}

      {screen === 'scan' && <>
        <Text style={s.title}>New scan · {selected?.name}</Text>
        <View style={s.card}>
          {image ? <Image accessibilityLabel="Selected leaf preview" source={{ uri: image.uri }} style={s.photo} /> : <Text style={s.placeholder}>Choose a clear leaf photo</Text>}
          <Button title="Capture leaf photo" disabled={busy} onPress={() => void pick(true)} />
          <Button title="Select from photos" secondary disabled={busy} onPress={() => void pick(false)} />
          <Text style={s.muted}>JPEG, PNG or WebP · maximum 10 MB · at least 224 × 224 pixels · at most 8192 pixels per side and 24 MP</Text>
          <Text style={s.notice}>Technical validation only. Plant recognition is not implemented: posters and unrelated photos may still pass. Please select a clear plant or leaf photo.</Text>
          <Button title="Validate image" disabled={busy || !image} onPress={() => void validateImage()} />
          {validation && <Text accessibilityRole={validation.is_valid ? undefined : 'alert'} style={validation.is_valid ? s.notice : s.error}>{validation.message}</Text>}
          {!validation?.is_valid && <Text style={s.muted}>Pass technical image validation to unlock environmental details and analysis.</Text>}
          {validation?.is_valid && <>
            <Field disabled={busy} label="Temperature (°C)" numeric value={temperature} setValue={value => { setTemperature(value); setPrediction(null); }} />
            <Field disabled={busy} label="Humidity (%)" numeric value={humidity} setValue={value => { setHumidity(value); setPrediction(null); }} />
            <Field disabled={busy} label="Soil type (e.g. Loamy, Clay, Sandy)" value={soilType} setValue={value => { setSoilType(value); setPrediction(null); }} />
            <Text style={s.label}>Soil condition</Text>
            <View style={s.row}>{(['Dry', 'Normal', 'Wet'] as SoilCondition[]).map(value =>
              <Button key={value} title={value} secondary={condition !== value} disabled={busy} onPress={() => { setCondition(value); setPrediction(null); }} />)}</View>
            <Text style={s.muted}>Enter environmental details manually. Only the image is sent to the predictor.</Text>
            <Button title="Start analysis (mock)" disabled={busy} onPress={() => void analyze()} />
            {prediction && <View style={s.card}>
              <Text style={s.title}>Analysis preview · not saved</Text>
              <Text style={s.title}>{prediction.disease}</Text>
              <Text style={s.metric}>{prediction.severity === null ? 'Severity not estimated' : `${prediction.severity}% severity`}</Text>
              <Text style={s.body}>{prediction.confidence}% confidence</Text>
              <Text style={s.notice}>{prediction.is_mock ? 'DEVELOPMENT MOCK • Synthetic demo result, not a diagnosis.' : prediction.predictor}</Text>
              <Button title="Save observation" disabled={busy} onPress={() => void saveScan()} />
            </View>}
          </>}
        </View>
      </>}
      {screen === 'result' && result && <>
        <Text style={s.title}>Scan saved · {selected?.name}</Text><Result observation={result} />
        <Button title="View plant history" disabled={busy} onPress={() => void openHistory('history')} />
        <Button title="Health dashboard" secondary disabled={busy} onPress={() => void openHistory('dashboard')} />
      </>}
      {screen === 'history' && <>
        <Text style={s.title}>{selected?.name} · History</Text>
        <Button title="Refresh history" secondary disabled={busy} onPress={() => void openHistory('history')} />
        <Button title="Health dashboard" disabled={busy} onPress={() => void openHistory('dashboard')} />
        {!observations.length && <Text style={s.muted}>No observations yet. Create a new scan to start this plant’s history.</Text>}
        {[...observations].reverse().map(observation => <Result key={observation.id} observation={observation} />)}
      </>}
      {screen === 'dashboard' && <>
        <Text style={s.title}>{selected?.name} · Health dashboard</Text>
        <Button title="Refresh dashboard" secondary disabled={busy} onPress={() => void openHistory('dashboard')} />
        <View style={s.card}><Text style={s.label}>Severity progression</Text>
          <Text style={s.muted}>Oldest → newest · fixed 0–100% scale{observations.some(item => item.is_mock) ? ' · includes synthetic demo values' : ''}</Text>
          {!latest ? <Text style={s.body}>Scan a leaf to begin tracking severity.</Text> : <>
            <Text style={s.metric}>{latest.severity === null ? 'Severity not estimated' : `${latest.severity}% latest severity`}</Text>
            <Text style={s.body}>{observations.length} observation{observations.length === 1 ? '' : 's'}</Text>
            <Text style={s.muted}>{observations.length > 1 && change !== null ? `${change > 0 ? '+' : ''}${change} percentage points since first scan` : 'Severity comparison requires two estimated values.'}</Text>
            {observations.map((observation, index) => <View key={observation.id} style={s.field}>
              <Text style={s.body}>#{index + 1} · {date(observation.created_at)} · {observation.severity === null ? 'Not estimated' : `${observation.severity}%`}</Text>
              {observation.severity !== null && <View style={s.track}><View style={[s.bar, { width: `${observation.severity}%` }]} /></View>}
            </View>)}
          </>}
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
