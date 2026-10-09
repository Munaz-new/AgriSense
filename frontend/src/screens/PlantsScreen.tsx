import React,{ useState } from 'react';
import { Image,Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { API_URL } from '../api';
import { s } from '../theme';
import { Button,Badge,Field,Title,date } from '../components/UI';
import { Icon } from '../components/Icon';
export function PlantsScreen({ j }: { j: Journal; }) {
  const [adding,setAdding]=useState(!j.plants.length||!!j.cropName);
  return <>
    <Title title="My Plants" subtitle="One profile for each physical plant." />
    <Button title={adding? 'Close plant form':'Add Plant'} icon="plus" disabled={j.locked} onPress={() => setAdding(!adding)} />
    {adding&&<View style={s.card}>
      <Text style={s.heading}>Meet your next plant</Text>
      <Field label="Plant name / identifier" value={j.name} setValue={j.setName} disabled={j.locked} />
      <Field label="Crop name (optional, user identified)" value={j.cropName} setValue={j.setCropName} disabled={j.locked} />
      <Button title="Set crop to tomato" secondary disabled={j.locked} onPress={() => j.setCropName('tomato')} />
      <Text style={s.muted}>Tomato analysis uses the crop field, not the plant name.</Text>
      <Button title="Save plant" disabled={j.locked||!j.name.trim()} onPress={() => void j.addPlant()} />
    </View>}
    {j.plants.map(plant => {
      const items=j.records[plant.id]; const latest=items?.[items.length-1]; return <View key={plant.id} style={[s.card,j.selected?.id===plant.id&&s.selected]}>
        <View style={s.row}>{latest? <Image accessibilityLabel={`Latest photo of ${plant.name}`} source={{ uri: `${API_URL}${latest.image_path}` }} style={s.thumbnail} />:<View style={[s.thumbnail,{ justifyContent: 'center',alignItems: 'center' }]}>
          <Icon name="plants" size={34} />
        </View>}<View style={[s.flex,{ gap: 5 }]}>
            <Text style={s.heading}>{plant.name}</Text>
            <Text style={s.muted}>{plant.crop_name||'Crop not recorded'}</Text>{j.selected?.id===plant.id&&<Badge>Selected</Badge>}</View>
        </View>
        <Text style={s.muted}>{items? `${items.length} observations`:'Records unavailable'}{latest? ` · Latest ${date(latest.observed_at||latest.created_at)}`:` · Added ${date(plant.created_at)}`}</Text>
        <Button title={j.selected?.id===plant.id? 'Selected plant':`Select ${plant.name}`} secondary disabled={j.locked||j.selected?.id===plant.id} onPress={() => j.selectPlant(plant)} />
        <Button title="New Observation" icon="scan" disabled={j.locked||!j.health?.capabilities.record_only} onPress={() => j.startScan(plant)} />
        <Button title="Plant History" secondary disabled={j.busy||(j.pendingId!==null&&j.selected?.id!==plant.id)} onPress={() => void j.openHistory('history',plant)} />
        <Button title="Health Dashboard" secondary disabled={j.busy||(j.pendingId!==null&&j.selected?.id!==plant.id)} onPress={() => void j.openHistory('dashboard',plant)} />
      </View>;
    })}<Button title="Refresh plants" secondary disabled={j.busy} onPress={() => void j.refresh()} />
  </>;
}
