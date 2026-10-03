import React from 'react';
import { Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { progressionLabel,recordLabels } from '../recordState';
import { s } from '../theme';
import { Button,Field,Title,date } from '../components/UI';
export function HealthScreen({ j }: { j: Journal; }) {
  return <>
    <Title title="Health dashboard" subtitle={`${j.selected?.name||'Plant'} · One plant, observed over time`} />
    <View style={s.card}>
      <Text style={s.eyebrow}>Severity comparison</Text>{j.progress&&<>
        <Text style={s.heading}>{progressionLabel(j.progress)}</Text>
        <Text style={s.body}>{j.observations.length>=2&&j.observations.every(o => o.severity===null)? 'Progression unavailable because severity was not measured.':j.progress.message}</Text>{j.progress.previous_observed_at&&j.progress.latest_observed_at&&<Text style={s.muted}>{date(j.progress.previous_observed_at)} → {date(j.progress.latest_observed_at)}</Text>}</>}
      <Text style={s.muted}>Health comparison requires validated severity measurements of the same leaf or site. Environmental context alone cannot establish progression.</Text>
      <Field label="Leaf / site reference to compare" value={j.progressRef} setValue={j.setProgressRef} disabled={j.busy} />
      <Button title="Refresh comparison" secondary disabled={j.busy} onPress={() => void j.openHistory('dashboard')} />
    </View>
    <View style={s.card}>
      <Text style={s.heading}>Recorded history</Text>
      <Text style={s.muted}>{j.observations.length} observations · Oldest → newest</Text>{!j.observations.length&&<Text style={s.body}>No observations yet.</Text>}{j.observations.map((o,i) => <View key={o.id} style={s.section}>
        <View style={s.divider} />
        <Text style={s.label}>Observation {i+1}</Text>
        <Text style={s.muted}>{date(o.observed_at||o.created_at)}{!o.observed_at? ' (save time)':''}</Text>
        <Text style={s.body}>{recordLabels(o).severity}</Text>{o.is_mock&&<Text style={s.notice}>Synthetic historical record · excluded from real progression</Text>}</View>)}</View>
    <Button title="Full observation history" disabled={j.busy} onPress={() => void j.openHistory('history')} />
  </>;
}
