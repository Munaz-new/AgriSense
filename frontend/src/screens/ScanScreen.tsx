import React from 'react';
import { isTomato } from '../recordState';
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
    {j.draftAvailable&&!j.image&&<View style={s.card}>
      <Text style={s.heading}>A draft is saved on this browser</Text>
      <Button title="Restore saved draft" disabled={j.busy} onPress={() => void j.restoreDraft()} />
      <Button title="Discard local recovery copy" secondary disabled={j.busy} onPress={j.forgetStoredDraft} />
    </View>}
    {!!j.draftMessage&&<Text accessibilityLiveRegion="polite" style={s.notice}>{j.draftMessage}</Text>}
    <Badge>{j.health?.capabilities.tomato_analysis? 'Tomato model available':'Photo record · analysis unavailable'}</Badge>
    <Text style={s.notice}>{j.health?.analysis_message||'Connect to the backend to check analysis availability.'}</Text>
    <Button title="Refresh connection and model status" secondary disabled={j.busy} onPress={() => void j.refresh()} />
    {!isTomato(j.selected)&&<View style={s.card}>
      <Text style={s.notice}>Tomato analysis needs a plant explicitly identified with crop “tomato”. A plant name alone does not set its crop.</Text>
      {j.plants.filter(isTomato).map(plant => <Button key={plant.id} title={`Select tomato plant: ${plant.name}`} disabled={j.locked} onPress={() => j.selectPlant(plant)} />)}
      <Button title="Create a tomato plant" secondary disabled={j.locked} onPress={() => { j.setCropName('tomato'); j.navigate('plants'); }} />
    </View>}
    {!j.plants.length? <>
      <Empty title="Add a plant first">Each photo belongs to one physical plant.</Empty>
      <Button title="Add Plant" icon="plus" onPress={() => j.navigate('plants')} />
    </>:<>
      <PlantPicker j={j} />
      <Text style={s.notice}>Selected crop: {j.selected?.crop_name||'Not recorded'}</Text>
      <View style={s.card}>
        <Text style={s.eyebrow}>01 / Plant photo</Text>{j.image? <Image key={`${j.imageRevision}:${j.image.uri}`} accessibilityLabel="Selected plant photo" source={{ uri: j.image.uri }} style={s.photo} />:<View style={s.placeholder}>
          <Icon name="scan" size={40} />
          <Text style={s.body}>Bring your plant into focus</Text>
          <Text style={s.muted}>Use a clear, well-lit photo.</Text>
        </View>}
        <Button title="Capture plant photo" icon="scan" disabled={j.locked||!j.selected} onPress={() => void j.pick(true)} />
        <Button title="Select from photos" secondary disabled={j.locked||!j.selected} onPress={() => void j.pick(false)} />
        <Text style={s.muted}>JPEG, PNG or WebP · up to 10 MB. Minimum 224 × 224 pixels; maximum 8192 per side and 24 MP.</Text>
        {j.image&&<Text style={s.notice}>Photo selected: {j.image.fileName||'Selected image'} · {j.validation?.is_valid? 'File validation passed':'File validation required'}</Text>}
        {j.image&&<Button title="Check file and plant suitability" secondary disabled={j.busy} onPress={() => void j.validateImage()} />}
        {j.image&&j.draftRecoverySupported&&<Button title="Keep draft on this browser" secondary disabled={j.locked} onPress={() => void j.keepDraft()} />}
        {j.draftRecoverySupported&&<Text style={s.muted}>Saving keeps a local photo and form recovery copy on this browser until the server confirms the save. Use one AgriSense tab; avoid shared devices. Browser data clearing removes this copy.</Text>}
        {j.validation&&!j.validation.is_valid&&<Text style={s.error}>Image rejected — file validation failed</Text>}
        {j.validation&&<Text style={j.validation.is_valid? s.notice:s.error}>{j.validation.message}</Text>}
        {j.image&&<View accessibilityLiveRegion="polite">
          <Text style={['rejected','inconclusive','unavailable'].includes(j.suitability.status)? s.error:s.notice}>{
            j.suitability.status==='accepted'? 'Plant-like content detected; tomato identity is not verified.':
            j.suitability.status==='rejected'? 'Image rejected — non-plant content':
            j.suitability.status==='inconclusive'? 'Image rejected for analysis — plant content uncertain':
            j.suitability.status==='checking'? 'Checking plant suitability…':
            j.suitability.status==='unavailable'? 'Plant suitability unavailable':'Plant suitability not checked'
          }</Text>
          {!!j.suitability.message&&<Text style={s.muted}>{j.suitability.message}</Text>}
        </View>}
        <Text style={s.muted}>File validation checks format and dimensions only; both leaves and logos can pass it. Plant suitability is a separate check. Neither step performs disease analysis or saves a record.</Text>
      </View>
      {j.validation?.is_valid&&<View style={s.card}>
        <Text style={s.eyebrow}>02 / Field context</Text>
        <Text style={s.heading}>What did you observe?</Text>
        <Text style={s.muted}>Optional, manually entered context only; these values are never model inputs. Enter only measured or observed values. Temperature supports -50 to 70°C; humidity supports 0 to 100%.</Text>
        <Field label="Temperature (°C, optional)" numeric disabled={j.locked} value={j.temperature} setValue={j.setTemperature} />
        <Field label="Humidity (%, optional)" numeric disabled={j.locked} value={j.humidity} setValue={j.setHumidity} />
        <Field label="Soil type (optional, up to 100 characters)" disabled={j.locked} value={j.soilType} setValue={j.setSoilType} />
        <Text style={s.label}>Soil condition</Text>
        <View style={s.wrap}>{(['Dry','Normal','Wet'] as SoilCondition[]).map(value => <Button key={value} title={value} secondary={j.condition!==value} disabled={j.locked} onPress={() => j.setCondition(value)} />)}</View>
        <Text style={s.label}>Observation time (automatic)</Text>
        <Text style={s.body}>{new Date(j.observedAt).toLocaleString()} · {j.observedTimezone}</Text>
        <Text style={s.muted}>Captured when you selected the photo, not its original camera date. Server save time is recorded separately.</Text>
        <Field label="Leaf / site reference (optional)" disabled={j.locked} value={j.trackingRef} setValue={j.setTrackingRef} />
        <Text style={s.muted}>A stable observation ID is generated on save. Add a reference only to track the same leaf or site. This alone does not establish comparable measurements.</Text>
        <Field label="Notes (optional, up to 2,000 characters)" maxLength={2000} multiline disabled={j.locked} value={j.notes} setValue={j.setNotes} />
        <Text style={s.notice}>Disease analysis has not completed for this draft. Analyze tomato leaf and save checks suitability again before classification. Screening can make mistakes and does not confirm tomato identity. Scores are uncalibrated; severity is not measured.</Text>
        {j.selected?.crop_name?.trim().toLowerCase()!=='tomato'&&<Text style={s.muted}>Select a plant with crop set to tomato to enable analysis. Other plants can still be recorded without analysis.</Text>}
        {j.analysisBlockers.length>0&&<Text style={s.notice}>Analyze disabled: {j.analysisBlockers.join(' ')}</Text>}
        <Button title={j.pendingId&&j.pendingAnalysis? 'Retry analysis and save':'Analyze tomato leaf and save'} disabled={j.analysisBlockers.length>0} onPress={() => void j.saveRecord(true)} />
        {j.recordBlockers.length>0&&<Text style={s.muted}>Save disabled: {j.recordBlockers.join(' ')}</Text>}
        <Button title={j.pendingId&&j.pendingAnalysis===false? 'Retry the same save':'Save observation without analysis'} disabled={j.recordBlockers.length>0} onPress={() => void j.saveRecord()} />
      </View>}
      {j.pendingId&&<View style={s.card}>
        <Text style={s.notice}>The save may already have completed. Retry uses the same request ID. {j.draftRecoverySupported? 'A recovery copy is kept on this browser. Restore it after reopening to check for a completed save.':'Keep this form open while checking history; native drafts are not retained after an app restart.'}</Text>
        <Button title="Check saved history" secondary disabled={j.busy} onPress={() => void j.openHistory('history')} />
        <Button title="Discard this form after checking history" secondary disabled={j.busy} onPress={j.clearDraft} />
        <Text style={s.muted}>Discarding the form does not delete any saved record.</Text>
      </View>}
    </>}</>;
}
