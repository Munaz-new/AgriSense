import React from 'react';
import { Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { s } from '../theme';
import { Button,Badge,Empty } from '../components/UI';
import { Icon } from '../components/Icon';
import { ObservationCard } from '../components/ObservationCard';
import { homeHealthSummary } from '../recordState';
export function HomeScreen({ j }: { j: Journal; }) {
  const all=Object.values(j.records).flat().sort((a,b) => (b.observed_at||b.created_at).localeCompare(a.observed_at||a.created_at));
  const count=j.selected? j.records[j.selected.id]?.length:undefined;
  return <>
    <View style={{ gap: 6 }}>
      <Text style={s.eyebrow}>Your growing journal</Text>
      <Text style={s.title}>A little closer to your plants.</Text>
      <Text style={s.muted}>Your plants, one observation at a time.</Text>
    </View>
    <View style={s.hero}>
      <View style={s.between}>
        <Text style={[s.eyebrow,{ color: '#D4E6C9' }]}>Observe · Record · Revisit</Text>
        <Icon name="plants" color="#D4E6C9" size={34} />
      </View>
      <Text style={s.heroTitle}>Every photo tells{'\n'}part of the story.</Text>
      <Text style={s.heroBody}>Keep a photo journal of the same plant, and see its observations together.</Text>
      <Button title="Scan Plant" icon="scan" secondary disabled={j.busy||!j.health?.capabilities.record_only} onPress={() => j.startScan()} />
    </View>
    <View style={s.row}>
      <View style={[s.card,s.flex]}>
        <Text style={s.metric}>{j.plants.length}</Text>
        <Text style={s.muted}>My plants</Text>
      </View>
      <View style={[s.card,s.flex]}>
        <Text style={s.metric}>{all.length}</Text>
        <Text style={s.muted}>Observations</Text>
      </View>
    </View>
    <View style={s.section}>
      <Text style={s.heading}>In your garden</Text>{j.selected? <View style={s.card}>
        <Badge>Selected plant</Badge>
        <Text style={s.heading}>{j.selected.name}</Text>
        <Text style={s.muted}>{j.selected.crop_name||'Crop not recorded'} · {count===undefined? 'Loading records…':`${count} observations`}</Text>
        <Button title="Plant history" secondary icon="history" disabled={j.busy} onPress={() => void j.openHistory('history')} />
        <Button title="Manage my plants" secondary disabled={j.locked} onPress={() => j.navigate('plants')} />
      </View>:<>
        <Empty title="Start with one plant">Give your plant a name and keep its observations in one place.</Empty>
        <Button title="Add your first plant" icon="plus" disabled={j.locked} onPress={() => j.navigate('plants')} />
      </>}</View>
    <View style={s.card}>
      <View style={s.row}>
        <Icon name="history" />
        <Text style={s.heading}>Health over time</Text>
      </View>
      <Text style={s.body}>{homeHealthSummary(j.selected? j.records[j.selected.id]:undefined)}</Text>
      <Text style={s.muted}>Repeated observations build a history. Health comparison needs validated severity measurements.</Text>{j.selected&&<Button title="Open health dashboard" secondary disabled={j.busy} onPress={() => void j.openHistory('dashboard')} />}</View>
    <View style={s.section}>
      <Text style={s.heading}>Recent observations</Text>{all.slice(0,2).map(o => <ObservationCard key={o.id} observation={o} plant={j.plants.find(p => p.id===o.plant_id)} compact />)}{!all.length&&<Text style={s.muted}>Your saved photos will appear here.</Text>}</View>
    <Text style={s.notice}>AI disease analysis will become available after the validated model is connected.</Text>
    <Button title="Refresh garden" secondary disabled={j.busy} onPress={() => void j.refresh()} />
  </>;
}
