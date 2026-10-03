import React,{ useEffect,useRef } from 'react';
import { ActivityIndicator,ScrollView,Text,View } from 'react-native';
import { SafeAreaProvider,SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import { useJournal } from './src/hooks/useJournal';
import { BottomNav,Screen } from './src/navigation/BottomNav';
import { HomeScreen } from './src/screens/HomeScreen';
import { PlantsScreen } from './src/screens/PlantsScreen';
import { ScanScreen } from './src/screens/ScanScreen';
import { HistoryScreen } from './src/screens/HistoryScreen';
import { HealthScreen } from './src/screens/HealthScreen';
import { MoreScreen } from './src/screens/MoreScreen';
import { ObservationCard } from './src/components/ObservationCard';
import { Button,Title } from './src/components/UI';
import { Icon } from './src/components/Icon';
import { s,colors } from './src/theme';
export default function App() {
  const j=useJournal();
  const scroll=useRef<ScrollView>(null);
  useEffect(() => { scroll.current?.scrollTo({ y: 0,animated: false }); },[j.screen]);
  function navigate(screen: Screen) {
    if(screen==='history'&&j.selected) void j.openHistory('history');
    else j.navigate(screen);
  }
  return <SafeAreaProvider>
    <SafeAreaView style={s.safe}>
      <StatusBar style="dark" />
      <View style={s.shell}>
        <View style={s.header}>
          <Icon name="plants" size={29} />
          <Text style={s.brand}>AgriSense</Text>
          <View style={s.flex} />
          <Text style={s.eyebrow}>Plant journal</Text>
        </View>
        <ScrollView ref={scroll} style={{ flex: 1 }} contentContainerStyle={s.page} keyboardShouldPersistTaps="handled">
          {j.error? <View style={s.section}>
            <Text accessibilityRole="alert" style={s.error}>{j.error}</Text>{!j.health&&<Button title="Reconnect" secondary disabled={j.busy} onPress={() => void j.refresh()} />}</View>:null}
          {j.busy&&<ActivityIndicator accessibilityLabel="Loading" color={colors.green} />}
          {j.pendingId&&j.screen!=='scan'&&<Button title="Return to pending record" disabled={j.busy} onPress={() => j.navigate('scan')} />}
          {j.screen==='home'&&<HomeScreen j={j} />}{j.screen==='plants'&&<PlantsScreen j={j} />}{j.screen==='scan'&&<ScanScreen j={j} />}{j.screen==='history'&&<HistoryScreen j={j} />}{j.screen==='dashboard'&&<HealthScreen j={j} />}{j.screen==='more'&&<MoreScreen j={j} />}
          {j.screen==='result'&&j.result&&<>
            <Title title="Observation saved" subtitle="Your photo and field context are in your journal." />
            <ObservationCard observation={j.result} plant={j.selected} />
            <Button title="View plant history" disabled={j.busy} onPress={() => void j.openHistory('history')} />
            <Button title="Health dashboard" secondary disabled={j.busy} onPress={() => void j.openHistory('dashboard')} />
          </>}
        </ScrollView>
        <BottomNav screen={j.screen} onNavigate={navigate} busy={j.busy} />
      </View>
    </SafeAreaView>
  </SafeAreaProvider>;
}
