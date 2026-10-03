import React from 'react';
import { Image,Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { SoilCondition } from '../api';
import { s } from '../theme';
import { Button,Field,Title,Empty,Badge } from '../components/UI';
import { PlantPicker } from '../components/PlantPicker';
import { Icon } from '../components/Icon';
export function ScanScreen({ j }: { j: Journal; }) {
  return <>
    <Title title="A new observation" subtitle="A photo today. A clearer history tomorrow." />
    <Badge>Photo record · AI analysis unavailable</Badge>
    {!j.plants.length? <>
      <Empty title="Add a plant first">Each photo belongs to one physical plant.</Empty>
      <Button title="Add Plant" icon="plus" onPress={() => j.navigate('plants')} />
    </>:<>
      <PlantPicker j={j} />
      <View style={s.card}>
        <Text style={s.eyebrow}>01 / Plant photo</Text>{j.image? <Image accessibilityLabel="Selected plant photo" source={{ uri: j.image.uri }} style={s.photo} />:<View style={s.placeholder}>
          <Icon name="scan" size={40} />
          <Text style={s.body}>Bring your plant into focus</Text>
          <Text style={s.muted}>Use a clear, well-lit photo.</Text>
        </View>}
        <Button title="Capture plant photo" icon="scan" disabled={j.locked||!j.selected} onPress={() => void j.pick(true)} />
        <Button title="Select from photos" secondary disabled={j.locked||!j.selected} onPress={() => void j.pick(false)} />
        <Text style={s.muted}>JPEG, PNG or WebP · up to 10 MB. Minimum 224 × 224 pixels; maximum 8192 per side and 24 MP.</Text>
        {j.image&&<Button title="Validate image" secondary disabled={j.locked} onPress={() => void j.validateImage()} />}
        {j.validation&&<Text style={j.validation.is_valid? s.notice:s.error}>{j.validation.message}</Text>}
        <Text style={s.muted}>Image validation checks file quality only. It does not identify a plant or detect disease.</Text>
      </View>
      {j.validation?.is_valid&&<View style={s.card}>
        <Text style={s.eyebrow}>02 / Field context</Text>
        <Text style={s.heading}>What did you observe?</Text>
        <Text style={s.muted}>Temperature, humidity and soil are required for this record. All other details are optional.</Text>
        <Field label="Temperature (°C)" numeric disabled={j.locked} value={j.temperature} setValue={j.setTemperature} />
        <Field label="Humidity (%)" numeric disabled={j.locked} value={j.humidity} setValue={j.setHumidity} />
        <Field label="Soil type" disabled={j.locked} value={j.soilType} setValue={j.setSoilType} />
        <Text style={s.label}>Soil condition</Text>
        <View style={s.wrap}>{(['Dry','Normal','Wet'] as SoilCondition[]).map(value => <Button key={value} title={value} secondary={j.condition!==value} disabled={j.locked} onPress={() => j.setCondition(value)} />)}</View>
        <Field label="Observed at (optional ISO time with timezone)" disabled={j.locked} value={j.observedAt} setValue={j.setObservedAt} />
        <Text style={s.muted}>Use YYYY-MM-DDTHH:mm:ss+05:30. Leave blank if unknown; save time is recorded separately.</Text>
        <Field label="Leaf / site reference (optional)" disabled={j.locked} value={j.trackingRef} setValue={j.setTrackingRef} />
        <Text style={s.muted}>Reuse a reference for the same leaf or site. This alone does not establish comparable measurements.</Text>
        <Field label="Notes (optional)" multiline disabled={j.locked} value={j.notes} setValue={j.setNotes} />
        <Text style={s.notice}>Your photo and context will be saved without validated disease analysis.</Text>
        <Button title={j.pendingId? 'Retry the same save':'Save observation without analysis'} disabled={j.busy||!j.health?.capabilities.record_only} onPress={() => void j.saveRecord()} />
      </View>}
      {j.pendingId&&<View style={s.card}>
        <Text style={s.notice}>The save may already have completed. Retry uses the same request ID. Keep this form open while checking history; drafts are not retained after an app restart.</Text>
        <Button title="Check saved history" secondary disabled={j.busy} onPress={() => void j.openHistory('history')} />
        <Button title="Discard this form after checking history" secondary disabled={j.busy} onPress={j.clearDraft} />
        <Text style={s.muted}>Discarding the form does not delete any saved record.</Text>
      </View>}
    </>}</>;
}
