import React,{ useState } from 'react';
import { Image,Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { API_URL } from '../api';
import { s } from '../theme';
import { Button,Badge,Field,Title,date } from '../components/UI';
import { Icon } from '../components/Icon';
export function PlantsScreen({ j }: { j: Journal; }) {
  const [adding,setAdding]=useState(!j.plants.length||j.cropChoice==='tomato'||!!j.pendingPlant);
  const [editing,setEditing]=useState<string|null>(null);
  const [editChoice,setEditChoice]=useState<'tomato'|'other'|'unknown'>('unknown');
  const [editOther,setEditOther]=useState('');
  return <>
    <Title title="My Plants" subtitle="One profile for each physical plant." />
    <Button title={adding? 'Close plant form':'Add Plant'} icon="plus" disabled={j.locked} onPress={() => setAdding(!adding)} />
    {adding&&<View style={s.card}>
      <Text style={s.heading}>Meet your next plant</Text>
      <Field label="Plant name / identifier" value={j.name} setValue={j.setName} disabled={j.locked} />
      <Text style={s.label}>Crop (choose what this plant is)</Text>
      <View style={s.wrap} accessibilityRole="radiogroup" accessibilityLabel="Choose the plant crop">
        <Button title="Tomato" selected={j.cropChoice==='tomato'} secondary={j.cropChoice!=='tomato'} disabled={j.locked} onPress={() => j.chooseCrop('tomato')} />
        <Button title="Other crop" selected={j.cropChoice==='other'} secondary={j.cropChoice!=='other'} disabled={j.locked} onPress={() => j.chooseCrop('other')} />
        <Button title="Not recorded" selected={j.cropChoice==='unknown'} secondary={j.cropChoice!=='unknown'} disabled={j.locked} onPress={() => j.chooseCrop('unknown')} />
      </View>
      {j.cropChoice==='other'&&<Field label="Other crop name" value={j.cropName} setValue={j.setCropName} disabled={j.locked} />}
      <Text style={s.muted}>The plant name is an identifier. Tomato analysis is available only when Crop is explicitly set to Tomato. Other crops and unrecorded crops can be saved as observations without analysis.</Text>
      <Button title={j.pendingPlant? 'Retry the same plant save':'Save plant'} disabled={j.busy||j.pendingId!==null||!j.name.trim()} onPress={() => void j.addPlant()} />
      {j.pendingPlant&&<>
        <Text style={s.notice}>The plant may already be saved. Refresh plants below, then retry with the same request ID. Keep this app open; after restarting, check the plant list before creating it again.</Text>
        <Button title="Unlock plant form after checking plants" secondary disabled={j.busy} onPress={j.discardPendingPlant} />
      </>}
    </View>}
    {j.plants.map(plant => {
      const items=j.records[plant.id]; const latest=items?.[items.length-1]; return <View key={plant.id} style={[s.card,j.selected?.id===plant.id&&s.selected]}>
        <View style={s.row}>{latest? <Image accessibilityLabel={`Latest photo of ${plant.name}`} source={{ uri: `${API_URL}${latest.image_path}` }} style={s.thumbnail} />:<View style={[s.thumbnail,{ justifyContent: 'center',alignItems: 'center' }]}>
          <Icon name="plants" size={34} />
        </View>}<View style={[s.flex,{ gap: 5 }]}>
            <Text style={s.heading}>{plant.name}</Text>
            <Text style={s.muted}>Crop: {plant.crop_name||'Not recorded'}</Text>{j.selected?.id===plant.id&&<Badge>Selected</Badge>}</View>
        </View>
        <Text style={s.muted}>{items? `${items.length} observations`:'Records unavailable'}{latest? ` · Latest ${date(latest.observed_at||latest.created_at)}`:` · Added ${date(plant.created_at)}`}</Text>
        <Button title={j.selected?.id===plant.id? 'Selected plant':`Select ${plant.name}`} secondary disabled={j.locked||j.selected?.id===plant.id} onPress={() => j.selectPlant(plant)} />
        {editing!==plant.id?<Button title={`Edit crop for ${plant.name}`} secondary disabled={j.locked} onPress={() => {
          setEditing(plant.id);
          setEditChoice(plant.crop_name?.trim().toLowerCase()==='tomato'?'tomato':plant.crop_name?'other':'unknown');
          setEditOther(plant.crop_name?.trim().toLowerCase()==='tomato'?'':plant.crop_name||'');
        }} />:<View style={s.card}>
          <Text style={s.notice}>Changing this label updates the existing plant and its history. Choose Tomato only if you have confirmed this plant is tomato.</Text>
          <View style={s.wrap} accessibilityRole="radiogroup" accessibilityLabel={`Choose crop for ${plant.name}`}>
            <Button title="Tomato" selected={editChoice==='tomato'} secondary={editChoice!=='tomato'} disabled={j.locked} onPress={() => setEditChoice('tomato')} />
            <Button title="Other crop" selected={editChoice==='other'} secondary={editChoice!=='other'} disabled={j.locked} onPress={() => setEditChoice('other')} />
            <Button title="Not recorded" selected={editChoice==='unknown'} secondary={editChoice!=='unknown'} disabled={j.locked} onPress={() => setEditChoice('unknown')} />
          </View>
          {editChoice==='other'&&<Field label={`Other crop name for ${plant.name}`} value={editOther} setValue={setEditOther} disabled={j.locked} />}
          <Button title={editChoice==='tomato'?`Save crop as Tomato for ${plant.name}`:editChoice==='other'?`Save crop as ${editOther.trim()||'Other'} for ${plant.name}`:`Mark crop unrecorded for ${plant.name}`} disabled={j.locked||(editChoice==='other'&&!editOther.trim())} onPress={() => void j.updatePlantCrop(plant.id,editChoice==='tomato'?'tomato':editChoice==='other'?editOther.trim():null).then(saved => { if(saved) setEditing(null); })} />
          <Button title="Cancel crop edit" secondary disabled={j.locked} onPress={() => setEditing(null)} />
        </View>}
        <Button title="New Observation" icon="scan" disabled={j.locked||!j.health?.capabilities.record_only} onPress={() => j.startScan(plant)} />
        <Button title="Plant History" secondary disabled={j.busy||(j.pendingId!==null&&j.selected?.id!==plant.id)} onPress={() => void j.openHistory('history',plant)} />
        <Button title="Health Dashboard" secondary disabled={j.busy||(j.pendingId!==null&&j.selected?.id!==plant.id)} onPress={() => void j.openHistory('dashboard',plant)} />
      </View>;
    })}<Button title="Refresh plants" secondary disabled={j.busy} onPress={() => void j.refresh()} />
  </>;
}
