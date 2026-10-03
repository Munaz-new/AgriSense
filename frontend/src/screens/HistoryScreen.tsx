import React from 'react';
import { Text } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { s } from '../theme';
import { Button,Title,Empty } from '../components/UI';
import { PlantPicker } from '../components/PlantPicker';
import { ObservationCard } from '../components/ObservationCard';
export function HistoryScreen({ j }: { j: Journal; }) {
  const items=j.selected? j.records[j.selected.id]:undefined;
  return <>
    <Title title="Observation history" subtitle="Small moments, saved over time." />{j.plants.length? <>
      <PlantPicker j={j} />
      <Text style={s.muted}>Newest first by observation time. Save time is used when observation time is unknown.</Text>
      <Button title="Health dashboard" secondary disabled={j.busy} onPress={() => void j.openHistory('dashboard')} />
      <Button title="Refresh history" secondary disabled={j.busy} onPress={() => void j.openHistory('history')} />{items===undefined? <Text style={s.muted}>History has not loaded. Refresh to try again.</Text>:items.length? [...items].reverse().map(o => <ObservationCard key={o.id} observation={o} plant={j.selected} />):<Empty title="Your story starts here">Save a photo observation to begin this plant’s history.</Empty>}<Button title="New observation" icon="scan" disabled={j.locked||!j.health?.capabilities.record_only} onPress={() => j.startScan()} />
    </>:<>
      <Empty title="No plants yet">Add your first plant to start a photo history.</Empty>
      <Button title="Add Plant" onPress={() => j.navigate('plants')} />
    </>}</>;
}
