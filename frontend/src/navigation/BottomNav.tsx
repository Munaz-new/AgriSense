import React from 'react';
import { Pressable,StyleSheet,Text,View } from 'react-native';
import { Icon,IconName } from '../components/Icon';
import { colors } from '../theme';
export type Screen='home'|'plants'|'scan'|'history'|'more'|'result'|'dashboard';
const tabs: { screen: Screen; label: string; icon: IconName; }[]=[
  { screen: 'home',label: 'Home',icon: 'home' },{ screen: 'plants',label: 'My Plants',icon: 'plants' },
  { screen: 'scan',label: 'Scan',icon: 'scan' },{ screen: 'history',label: 'History',icon: 'history' },{ screen: 'more',label: 'More',icon: 'more' },
];
export function BottomNav({ screen,onNavigate,busy }: { screen: Screen; onNavigate: (screen: Screen) => void; busy: boolean; }) {
  const active=screen==='result'? 'scan':screen==='dashboard'? 'history':screen;
  return <View accessibilityRole="tablist" style={styles.bar}>{tabs.map(tab => <Pressable key={tab.screen} accessibilityRole="tab" accessibilityLabel={tab.label} accessibilityState={{ selected: active===tab.screen,disabled: busy }} disabled={busy} onPress={() => onNavigate(tab.screen)} style={styles.tab}>
    <View style={[styles.icon,tab.screen==='scan'&&styles.scan,active===tab.screen&&tab.screen!=='scan'&&{ backgroundColor: colors.pale }]}>
      <Icon name={tab.icon} color={tab.screen==='scan'? '#FFF':active===tab.screen? colors.green:colors.muted} />
    </View>
    <Text style={[styles.label,active===tab.screen&&{ color: colors.green,fontWeight: '800' }]}>{tab.label}</Text>
  </Pressable>)}</View>;
}
const styles=StyleSheet.create({ bar: { flexDirection: 'row',borderTopWidth: 1,borderColor: colors.line,backgroundColor: '#FFF',paddingTop: 7,paddingBottom: 6,paddingHorizontal: 7 },tab: { flex: 1,alignItems: 'center',justifyContent: 'center',minHeight: 65,gap: 4 },icon: { width: 43,height: 33,alignItems: 'center',justifyContent: 'center',borderRadius: 16 },scan: { backgroundColor: colors.green,width: 49,height: 40,borderRadius: 16 },label: { fontSize: 10,color: colors.muted } });
