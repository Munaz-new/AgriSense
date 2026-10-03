import React from 'react';
import { ScrollView,Pressable,Text,View } from 'react-native';
import { Journal } from '../hooks/useJournal';
import { s } from '../theme';
export function PlantPicker({ j }: { j: Journal; }) {
  return <View style={s.section}>
    <Text style={s.label}>Selected plant</Text>
    <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={s.row}>{j.plants.map(plant => <Pressable key={plant.id} accessibilityRole="button" accessibilityLabel={`Select ${plant.name}`} accessibilityState={{ selected: j.selected?.id===plant.id,disabled: j.locked }} disabled={j.locked} onPress={() => j.selectPlant(plant)} style={[s.button,s.secondary,j.selected?.id===plant.id&&s.selected,{ borderWidth: 1,borderColor: j.selected?.id===plant.id? '#216449':'transparent',maxWidth: 230 }]}>
      <Text style={[s.buttonText,s.secondaryText]}>{plant.name}</Text>
    </Pressable>)}</ScrollView>
  </View>;
}
