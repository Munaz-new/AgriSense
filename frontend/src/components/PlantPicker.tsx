import React from 'react';
import { ScrollView,Pressable,Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { s } from '../theme';
export function PlantPicker({ j }: { j: Journal; }) {
  return <View style={s.section}>
    <Text style={s.label}>Selected plant</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={s.row}>{j.plants.map(plant => <Pressable key={plant.id} accessibilityRole="button" accessibilityLabel={`Select plant ${plant.name}, crop ${plant.crop_name||'not recorded'}`} accessibilityState={{ selected: j.selected?.id===plant.id,disabled: j.locked }} disabled={j.locked} onPress={() => j.selectPlant(plant)} style={[s.button,s.secondary,j.selected?.id===plant.id&&s.selected,{ borderWidth: 1,borderColor: j.selected?.id===plant.id? '#216449':'transparent',maxWidth: 230,alignItems:'flex-start' }]}>
      <Text style={[s.buttonText,s.secondaryText]} numberOfLines={1}>{plant.name}</Text>
      <Text style={[s.muted,{ fontSize: 12 }]} numberOfLines={1}>Crop: {plant.crop_name||'Not recorded'}</Text>
    </Pressable>)}</ScrollView>
  </View>;
}
