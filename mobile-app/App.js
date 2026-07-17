import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { requestRecordingPermissionsAsync, setAudioModeAsync } from 'expo-audio';
import { StatusBar } from 'expo-status-bar';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useAudioRecorder } from '@siteed/audio-studio';

const BACKEND_ORIGIN = 'https://store.mkjewels.net';
const TARGET_SAMPLE_RATE = 16000;
const MAX_RECONNECT_ATTEMPTS = 5;
const AUTH_TTL_MS = 12 * 60 * 60 * 1000;
const SHOW_DEBUG_PANEL = __DEV__;
const SESSION_END_FLUSH_TIMEOUT_MS = 1500;
const SESSION_END_POLL_INTERVAL_MS = 50;

function buildWebSocketUrl({ salesperson, store }) {
  const wsOrigin = BACKEND_ORIGIN.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
  const name = encodeURIComponent((salesperson?.name || 'Unknown').trim());
  return `${wsOrigin}/ws?name=${name}&salesperson_id=${salesperson.id}&store_id=${store.id}`;
}

function base64ToArrayBuffer(base64) {
  const binary = globalThis.atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes.buffer;
}

function getAuthStorageKey(salespersonId) {
  return `mkj_auth_${salespersonId}`;
}

function describeWebSocketError(error) {
  try {
    return JSON.stringify(error, Object.getOwnPropertyNames(error));
  } catch {
    return String(error);
  }
}

export default function App() {
  const recorder = useAudioRecorder();
  const socketRef = useRef(null);
  const streamActiveRef = useRef(false);
  const userInitiatedStopRef = useRef(false);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const readinessTimerRef = useRef(null);
  const recordingStartedAtRef = useRef(0);

  const [stores, setStores] = useState([]);
  const [salespersons, setSalespersons] = useState([]);
  const [selectedStore, setSelectedStore] = useState(null);
  const [selectedSalesperson, setSelectedSalesperson] = useState(null);
  const [authenticatedSalesperson, setAuthenticatedSalesperson] = useState(null);
  const [rememberedAuth, setRememberedAuth] = useState(null);
  const [pin, setPin] = useState('');
  const [confirmPin, setConfirmPin] = useState('');
  const [pinMode, setPinMode] = useState('existing');
  const [pinMessage, setPinMessage] = useState('');
  const [screen, setScreen] = useState('store');
  const [isConnected, setIsConnected] = useState(false);
  const [isSystemReady, setIsSystemReady] = useState(false);
  const [readinessMessage, setReadinessMessage] = useState('Connecting to server...');
  const [statusMessage, setStatusMessage] = useState('');
  const [debugMessages, setDebugMessages] = useState([]);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [interruptionState, setInterruptionState] = useState(null);
  const [loadingStores, setLoadingStores] = useState(true);
  const [loadingSalespersons, setLoadingSalespersons] = useState(false);
  const [authSubmitting, setAuthSubmitting] = useState(false);

  const isRecording = recorder.isRecording;
  const hasActiveRecordingSession = isRecording && recordingStartedAtRef.current > 0;
  const showInterruptionBanner = Boolean(interruptionState && hasActiveRecordingSession);

  const fetchJson = useCallback(async (path, options = {}) => {
    const response = await fetch(`${BACKEND_ORIGIN}${path}`, options);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  }, []);

  const logDebug = useCallback((level, message, details = null) => {
    const timestamp = new Date().toISOString();
    const detailText = details === null ? '' : ` ${typeof details === 'string' ? details : JSON.stringify(details)}`;
    const line = `[${timestamp}] ${message}${detailText}`;

    if (level === 'warn') {
      console.warn(line);
    } else {
      console.log(line);
    }

    setDebugMessages((current) => [line, ...current].slice(0, 8));
  }, []);

  useEffect(() => {
    async function configureAudio() {
      const permission = await requestRecordingPermissionsAsync();
      if (!permission.granted) {
        Alert.alert('Microphone permission required', 'Allow microphone access to record sales conversations.');
      }
      await setAudioModeAsync({
        playsInSilentMode: true,
        allowsRecording: true,
        allowsBackgroundRecording: true,
      });
    }

    configureAudio().catch((error) => {
      setStatusMessage(`Audio setup failed: ${error.message}`);
    });
  }, []);

  useEffect(() => {
    async function loadStores() {
      try {
        const data = await fetchJson('/api/stores');
        setStores(data.stores || data || []);
      } catch (error) {
        setStatusMessage(`Unable to load stores: ${error.message}`);
      } finally {
        setLoadingStores(false);
      }
    }

    loadStores();
  }, [fetchJson]);

  useEffect(() => {
    if (!selectedStore) {
      return;
    }

    async function loadSalespersons() {
      setLoadingSalespersons(true);
      setSalespersons([]);
      setSelectedSalesperson(null);
      setRememberedAuth(null);
      try {
        const data = await fetchJson(`/api/stores/${selectedStore.id}/salespersons`);
        setSalespersons(data.salespersons || data || []);
      } catch (error) {
        setStatusMessage(`Unable to load salespersons: ${error.message}`);
      } finally {
        setLoadingSalespersons(false);
      }
    }

    loadSalespersons();
  }, [fetchJson, selectedStore]);

  useEffect(() => {
    if (!selectedSalesperson) {
      setRememberedAuth(null);
      return;
    }

    let cancelled = false;
    async function loadRememberedAuth() {
      const key = getAuthStorageKey(selectedSalesperson.id);
      const raw = await AsyncStorage.getItem(key);
      if (!raw) {
        if (!cancelled) {
          setRememberedAuth(null);
        }
        return;
      }

      try {
        const stored = JSON.parse(raw);
        if (stored.expires > Date.now() && stored.salesperson_id === selectedSalesperson.id) {
          if (!cancelled) {
            setRememberedAuth(stored);
          }
        } else {
          await AsyncStorage.removeItem(key);
          if (!cancelled) {
            setRememberedAuth(null);
          }
        }
      } catch {
        await AsyncStorage.removeItem(key);
        if (!cancelled) {
          setRememberedAuth(null);
        }
      }
    }

    loadRememberedAuth().catch(() => {
      if (!cancelled) {
        setRememberedAuth(null);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [selectedSalesperson]);

  useEffect(() => {
    if (!isRecording) {
      setElapsedSeconds(0);
      return undefined;
    }

    const timer = setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - recordingStartedAtRef.current) / 1000));
    }, 1000);
    return () => clearInterval(timer);
  }, [isRecording]);

  const checkReadiness = useCallback(async () => {
    if (readinessTimerRef.current) {
      clearTimeout(readinessTimerRef.current);
      readinessTimerRef.current = null;
    }

    try {
      const health = await fetchJson('/api/health');
      if (health.status === 'ready') {
        setIsSystemReady(true);
        setReadinessMessage('');
        return;
      }
      setIsSystemReady(false);
      setReadinessMessage('Starting up... please wait');
    } catch {
      setIsSystemReady(false);
      setReadinessMessage('Connecting to server...');
    }

    readinessTimerRef.current = setTimeout(checkReadiness, 5000);
  }, [fetchJson]);

  useEffect(() => {
    if (screen === 'recording') {
      checkReadiness();
    }
    return () => {
      if (readinessTimerRef.current) {
        clearTimeout(readinessTimerRef.current);
      }
    };
  }, [checkReadiness, screen]);

  const completeSalespersonAuth = useCallback(async (salesperson, persistAuth) => {
    if (salesperson.store_id !== selectedStore.id) {
      throw new Error('Salesperson store mismatch');
    }

    if (persistAuth) {
      await AsyncStorage.setItem(
        getAuthStorageKey(salesperson.id),
        JSON.stringify({
          salesperson_id: salesperson.id,
          name: salesperson.name,
          store_id: salesperson.store_id,
          designation: salesperson.designation,
          expires: Date.now() + AUTH_TTL_MS,
        })
      );
    }

    setAuthenticatedSalesperson(salesperson);
    setPin('');
    setConfirmPin('');
    setPinMessage('');
    setScreen('recording');
  }, [selectedStore]);

  const handlePinSubmit = useCallback(async () => {
    if (!selectedSalesperson || !/^\d{4}$/.test(pin)) {
      setPinMessage('Enter a 4-digit PIN');
      return;
    }

    if (pinMode === 'setup' && pin !== confirmPin) {
      setPinMessage("PINs don't match");
      return;
    }

    setAuthSubmitting(true);
    setPinMessage(pinMode === 'setup' ? 'Setting PIN...' : 'Checking PIN...');
    try {
      if (pinMode === 'setup') {
        const result = await fetchJson('/api/auth/salesperson/set-first-pin', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ salesperson_id: selectedSalesperson.id, pin }),
        });
        if (!result.success) {
          throw new Error(result.error || 'Unable to set PIN');
        }
        await completeSalespersonAuth(selectedSalesperson, true);
        return;
      }

      const result = await fetchJson('/api/auth/salesperson', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ salesperson_id: selectedSalesperson.id, pin }),
      });
      if (result.success) {
        await completeSalespersonAuth(selectedSalesperson, true);
        return;
      }
      if (result.reason === 'NO_PIN_SET') {
        setPinMode('setup');
        setPin('');
        setPinMessage('First time? Set your PIN.');
        return;
      }
      throw new Error(result.error || 'Incorrect PIN');
    } catch (error) {
      if (String(error.message).includes('NO_PIN_SET')) {
        setPinMode('setup');
        setPin('');
        setPinMessage('First time? Set your PIN.');
      } else {
        setPinMessage(error.message);
      }
    } finally {
      setAuthSubmitting(false);
    }
  }, [completeSalespersonAuth, confirmPin, fetchJson, pin, pinMode, selectedSalesperson]);

  const sendRecorderEvent = useCallback((eventType, detail, metadata = {}) => {
    const websocket = socketRef.current;
    if (!websocket || websocket.readyState !== WebSocket.OPEN) {
      return;
    }

    websocket.send(JSON.stringify({
      type: 'recorder_event',
      event_type: eventType,
      detail,
      timestamp: new Date().toISOString(),
      metadata,
    }));
  }, []);

  const clearInterruption = useCallback((reason) => {
    setInterruptionState((current) => {
      if (!current) {
        return null;
      }
      sendRecorderEvent('audio_track_resumed', `Recording resumed after ${current.reason}.`, {
        reason,
        interruptedForMs: Date.now() - Date.parse(current.occurredAt),
      });
      return null;
    });
    setStatusMessage('');
  }, [sendRecorderEvent]);

  const showInterruption = useCallback((reason, recoverable) => {
    if (!hasActiveRecordingSession) {
      return;
    }

    const occurredAt = new Date().toISOString();
    setInterruptionState({ reason, recoverable, occurredAt });
    setStatusMessage('Recording interrupted. Tap Resume recording to continue.');
    sendRecorderEvent(`audio_track_${reason}`, `Recording interrupted: audio track ${reason}.`, {
      occurredAt,
      recoverable,
    });
  }, [hasActiveRecordingSession, sendRecorderEvent]);

  const closeSocket = useCallback((reason, metadata = {}) => {
    const websocket = socketRef.current;
    const readyState = websocket?.readyState ?? 'none';
    logDebug('warn', `WebSocket close called from: ${reason || 'unknown'}`, {
      readyState,
      streamActive: streamActiveRef.current,
      userInitiatedStop: userInitiatedStopRef.current,
      reconnectAttempts: reconnectAttemptsRef.current,
      ...metadata,
    });
    socketRef.current = null;
    setIsConnected(false);
    if (
      websocket
      && (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING)
    ) {
      websocket.close();
    }
  }, [logDebug]);

  const endSessionAndCloseSocket = useCallback(async () => {
    const websocket = socketRef.current;
    if (!websocket) {
      return;
    }

    const deadline = Date.now() + SESSION_END_FLUSH_TIMEOUT_MS;
    while (websocket.readyState === WebSocket.CONNECTING && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, SESSION_END_POLL_INTERVAL_MS));
    }

    if (websocket.readyState === WebSocket.OPEN) {
      const sessionEndMessage = JSON.stringify({
        type: 'session_end',
        reason: 'user_stopped',
      });
      websocket.send(sessionEndMessage);
      logDebug('log', 'WebSocket session_end sent', sessionEndMessage);

      while (
        websocket.readyState === WebSocket.OPEN
        && websocket.bufferedAmount > 0
        && Date.now() < deadline
      ) {
        await new Promise((resolve) => setTimeout(resolve, SESSION_END_POLL_INTERVAL_MS));
      }
    } else {
      logDebug('warn', 'WebSocket session_end not sent before close', {
        readyState: websocket.readyState,
        timedOut: Date.now() >= deadline,
      });
    }

    if (socketRef.current === websocket) {
      socketRef.current = null;
      setIsConnected(false);
    }
    if (websocket.readyState === WebSocket.OPEN || websocket.readyState === WebSocket.CONNECTING) {
      websocket.close();
    }
  }, [logDebug]);

  const stopRecording = useCallback(async (message) => {
    userInitiatedStopRef.current = true;
    streamActiveRef.current = false;
    reconnectAttemptsRef.current = 0;
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    setInterruptionState(null);
    recordingStartedAtRef.current = 0;
    await endSessionAndCloseSocket();
    if (recorder.isRecording) {
      await recorder.stopRecording();
    }
    setStatusMessage(message || '');
  }, [endSessionAndCloseSocket, recorder]);

  const scheduleReconnect = useCallback(() => {
    if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
      setStatusMessage(`Connection failed after ${MAX_RECONNECT_ATTEMPTS} attempts. Tap Start to retry.`);
      logDebug('warn', 'stopRecording requested from: reconnect attempts exhausted', {
        maxReconnectAttempts: MAX_RECONNECT_ATTEMPTS,
      });
      stopRecording().catch((error) => setStatusMessage(`Stop failed: ${error.message}`));
      return;
    }

    reconnectAttemptsRef.current += 1;
    const attempt = reconnectAttemptsRef.current;
    const delaySeconds = Math.min(2 ** (attempt - 1), 16);
    setStatusMessage(`Connection lost. Reconnecting in ${delaySeconds}s... (attempt ${attempt}/${MAX_RECONNECT_ATTEMPTS})`);

    reconnectTimerRef.current = setTimeout(() => {
      if (streamActiveRef.current && !userInitiatedStopRef.current) {
        connectWebSocket();
      }
    }, delaySeconds * 1000);
  }, [stopRecording]);

  const connectWebSocket = useCallback(() => {
    if (!authenticatedSalesperson || !selectedStore) {
      return;
    }

    const websocketUrl = buildWebSocketUrl({
      salesperson: authenticatedSalesperson,
      store: selectedStore,
    });
    const captureSettingsMessage = {
      type: 'capture_settings',
      audioContextSampleRate: TARGET_SAMPLE_RATE,
      captureProcessor: '@siteed/audio-studio',
      trackSettings: {
        sampleRate: TARGET_SAMPLE_RATE,
        channelCount: 1,
        bitDepth: 16,
        platform: Platform.OS,
      },
    };
    const firstMessageJson = JSON.stringify(captureSettingsMessage);

    logDebug('log', 'WebSocket connecting', {
      url: websocketUrl,
      salesperson_id: authenticatedSalesperson.id,
      store_id: selectedStore.id,
    });

    const websocket = new WebSocket(websocketUrl);
    socketRef.current = websocket;

    websocket.onopen = () => {
      logDebug('log', 'WebSocket onopen fired');
      reconnectAttemptsRef.current = 0;
      setIsConnected(true);
      setStatusMessage('');
      logDebug('log', 'WebSocket first message', firstMessageJson);
      websocket.send(firstMessageJson);
    };

    websocket.onclose = (event) => {
      const code = event?.code ?? 'unknown';
      const reason = event?.reason || '';
      logDebug('warn', 'WebSocket onclose', {
        code,
        reason,
        currentSocketMatches: socketRef.current === websocket,
        streamActive: streamActiveRef.current,
        userInitiatedStop: userInitiatedStopRef.current,
        reconnectAttempts: reconnectAttemptsRef.current,
      });
      if (socketRef.current !== websocket) {
        return;
      }
      setIsConnected(false);
      socketRef.current = null;
      if (reason) {
        setStatusMessage(`Connection closed (${code}): ${reason}`);
      }
      if (streamActiveRef.current && !userInitiatedStopRef.current) {
        scheduleReconnect();
      }
    };

    websocket.onerror = (error) => {
      logDebug('warn', 'WebSocket onerror', describeWebSocketError(error));
      setIsConnected(false);
      if (!streamActiveRef.current) {
        setStatusMessage('WebSocket error. Check the recorder backend.');
      }
    };
  }, [authenticatedSalesperson, logDebug, scheduleReconnect, selectedStore]);

  const startRecording = useCallback(async () => {
    if (!isSystemReady) {
      setStatusMessage('System is warming up, please wait...');
      return;
    }
    if (!selectedStore || !authenticatedSalesperson) {
      setStatusMessage('Verify your PIN before recording.');
      return;
    }

    userInitiatedStopRef.current = false;
    streamActiveRef.current = true;
    reconnectAttemptsRef.current = 0;
    setStatusMessage('Starting microphone...');
    setInterruptionState(null);

    try {
      await recorder.startRecording({
        sampleRate: TARGET_SAMPLE_RATE,
        channels: 1,
        encoding: 'pcm_16bit',
        interval: 250,
        keepAwake: true,
        showNotification: true,
        notification: {
          title: 'MK Jewels Recorder',
          text: 'Recording audio',
          android: {
            channelId: 'mkjewels-recorder',
            channelName: 'MK Jewels Recorder',
            channelDescription: 'Active sales floor recording',
            priority: 'high',
            accentColor: '#C9A96E',
          },
        },
        android: {
          audioFocusStrategy: 'background',
        },
        output: {
          primary: { enabled: false },
          compressed: { enabled: false },
        },
        streamFormat: 'raw',
        bufferDurationSeconds: 0.1,
        autoResumeAfterInterruption: true,
        onRecordingInterrupted: (event) => {
          logDebug('warn', 'Recording interruption event', event);
          if (event.isPaused) {
            showInterruption(event.reason, true);
          } else {
            clearInterruption(event.reason);
          }
        },
        onMaxDurationReached: (event) => {
          logDebug('warn', 'Recorder max duration reached', event);
        },
        onRecordingStopped: (_recording, reason) => {
          logDebug('warn', 'Recorder stopped callback', { reason });
        },
        onAudioStream: async (event) => {
          const websocket = socketRef.current;
          if (!streamActiveRef.current || !websocket || websocket.readyState !== WebSocket.OPEN) {
            return;
          }

          if (typeof event.data === 'string') {
            websocket.send(base64ToArrayBuffer(event.data));
          } else if (event.data?.buffer) {
            websocket.send(event.data.buffer);
          }
        },
      });
      recordingStartedAtRef.current = Date.now();
      setStatusMessage('Connecting...');
      connectWebSocket();
    } catch (error) {
      logDebug('warn', 'Recorder start failed before WebSocket connect', error?.message || String(error));
      streamActiveRef.current = false;
      closeSocket('startRecording catch', { error: error?.message || String(error) });
      setStatusMessage(`Unable to start recording: ${error.message}`);
      setInterruptionState(null);
    }
  }, [
    authenticatedSalesperson,
    clearInterruption,
    closeSocket,
    connectWebSocket,
    isSystemReady,
    logDebug,
    recorder,
    selectedStore,
    showInterruption,
  ]);

  const resumeInterruptedRecording = useCallback(async () => {
    if (!interruptionState) {
      return;
    }
    if (interruptionState.recoverable) {
      clearInterruption('manual_resume');
      return;
    }
    sendRecorderEvent('audio_track_manual_restart', 'User tapped resume after audio track ended.');
    await stopRecording('Restarting recording...');
    await startRecording();
  }, [clearInterruption, interruptionState, sendRecorderEvent, startRecording, stopRecording]);

  const signOut = useCallback(() => {
    if (authenticatedSalesperson) {
      AsyncStorage.removeItem(getAuthStorageKey(authenticatedSalesperson.id));
    }
    setAuthenticatedSalesperson(null);
    setSelectedSalesperson(null);
    setRememberedAuth(null);
    setPin('');
    setConfirmPin('');
    setPinMessage('');
    setScreen('store');
  }, [authenticatedSalesperson]);

  const canStart = isSystemReady && !isRecording;
  const salespersonOptions = useMemo(
    () => salespersons.map((person) => ({ ...person, key: String(person.id) })),
    [salespersons]
  );

  function renderStoreScreen() {
    return (
      <View style={styles.screen}>
        <View style={styles.header}>
          <Text style={styles.logo}>MK JEWELS</Text>
          <Text style={styles.overline}>Sales floor recorder</Text>
          <Text style={styles.title}>Select Your Store</Text>
        </View>
        {loadingStores ? <ActivityIndicator color="#A07840" /> : (
          <FlatList
            data={stores}
            keyExtractor={(item) => String(item.id)}
            renderItem={({ item }) => (
              <Pressable
                style={styles.selectionButton}
                onPress={() => {
                  setSelectedStore(item);
                  setScreen('salesperson');
                  setStatusMessage('');
                }}
              >
                <Text style={styles.selectionTitle}>{item.name}</Text>
              </Pressable>
            )}
          />
        )}
      </View>
    );
  }

  function renderSalespersonScreen() {
    return (
      <ScrollView contentContainerStyle={styles.screen}>
        <Pressable style={styles.backButton} onPress={() => setScreen('store')}>
          <Text style={styles.backText}>{'< Back'}</Text>
        </Pressable>
        <View style={styles.header}>
          <Text style={styles.logo}>MK JEWELS</Text>
          <Text style={styles.overline}>Team selection</Text>
          <Text style={styles.title}>Who are you?</Text>
          <Text style={styles.subheading}>{selectedStore?.name}</Text>
        </View>

        {loadingSalespersons ? <ActivityIndicator color="#A07840" /> : (
          <View style={styles.list}>
            {salespersonOptions.map((person) => (
              <Pressable
                key={person.key}
                style={[
                  styles.selectionButton,
                  selectedSalesperson?.id === person.id && styles.selectedButton,
                ]}
                onPress={() => {
                  setSelectedSalesperson(person);
                  setPinMode('existing');
                  setPin('');
                  setConfirmPin('');
                  setPinMessage('');
                }}
              >
                <Text style={styles.selectionTitle}>{person.name}</Text>
                <Text style={styles.selectionMeta}>{person.designation}</Text>
              </Pressable>
            ))}
          </View>
        )}

        {selectedSalesperson && rememberedAuth ? (
          <View style={styles.rememberedAuth}>
            <Text style={styles.rememberedText}>Continue as {rememberedAuth.name}</Text>
            <Pressable
              style={styles.primaryButton}
              onPress={() => completeSalespersonAuth(selectedSalesperson, false)}
            >
              <Text style={styles.primaryButtonText}>Continue</Text>
            </Pressable>
            <Pressable
              onPress={() => {
                AsyncStorage.removeItem(getAuthStorageKey(selectedSalesperson.id));
                setRememberedAuth(null);
              }}
            >
              <Text style={styles.linkText}>Not you? Change</Text>
            </Pressable>
          </View>
        ) : null}

        {selectedSalesperson && !rememberedAuth ? (
          <View style={styles.pinCard}>
            {pinMode === 'setup' ? <Text style={styles.setupBanner}>First time? Set your PIN.</Text> : null}
            <Text style={styles.stepHeading}>{pinMode === 'setup' ? 'Set your PIN' : 'Enter your PIN'}</Text>
            <TextInput
              style={styles.pinInput}
              keyboardType="number-pad"
              maxLength={4}
              secureTextEntry
              value={pin}
              onChangeText={setPin}
              placeholder="0000"
              placeholderTextColor="#B7A894"
            />
            {pinMode === 'setup' ? (
              <TextInput
                style={styles.pinInput}
                keyboardType="number-pad"
                maxLength={4}
                secureTextEntry
                value={confirmPin}
                onChangeText={setConfirmPin}
                placeholder="Confirm PIN"
                placeholderTextColor="#B7A894"
              />
            ) : null}
            {pinMessage ? <Text style={styles.pinMessage}>{pinMessage}</Text> : null}
            <Pressable
              style={[styles.primaryButton, authSubmitting && styles.disabledButton]}
              disabled={authSubmitting}
              onPress={handlePinSubmit}
            >
              <Text style={styles.primaryButtonText}>{authSubmitting ? 'Please wait...' : 'Continue'}</Text>
            </Pressable>
          </View>
        ) : null}
      </ScrollView>
    );
  }

  function renderRecordingScreen() {
    return (
      <ScrollView contentContainerStyle={styles.screen}>
        <Pressable style={styles.signOutButton} onPress={signOut}>
          <Text style={styles.linkText}>Sign out</Text>
        </Pressable>
        <View style={styles.header}>
          <Text style={styles.logo}>MK JEWELS</Text>
          <Text style={styles.overline}>Recorder ready</Text>
          <Text style={styles.title}>Sales Recording</Text>
        </View>

        <View style={styles.identityGrid}>
          <View style={styles.identityItem}>
            <Text style={styles.label}>Store</Text>
            <Text style={styles.identityValue}>{selectedStore?.name}</Text>
          </View>
          <View style={styles.identityItem}>
            <Text style={styles.label}>Salesperson</Text>
            <Text style={styles.identityValue}>{authenticatedSalesperson?.name}</Text>
            <Text style={styles.selectionMeta}>{authenticatedSalesperson?.designation}</Text>
          </View>
        </View>

        {readinessMessage ? <Text style={styles.readinessMessage}>{readinessMessage}</Text> : null}

        {showInterruptionBanner ? (
          <View style={styles.interruptionBanner}>
            <Text style={styles.interruptionTitle}>Recording interrupted</Text>
            <Text style={styles.interruptionText}>Tap Resume recording to continue.</Text>
            <Pressable style={styles.interruptionButton} onPress={resumeInterruptedRecording}>
              <Text style={styles.interruptionButtonText}>Resume recording</Text>
            </Pressable>
          </View>
        ) : null}

        <Pressable
          style={[
            styles.recordButton,
            isRecording && styles.recordButtonActive,
            !canStart && !isRecording && styles.disabledButton,
          ]}
          disabled={!canStart && !isRecording}
          onPress={isRecording ? () => stopRecording('Recording stopped.') : startRecording}
        >
          <View style={isRecording ? styles.stopIcon : styles.recordIcon} />
          <Text style={[styles.recordButtonText, isRecording && styles.recordButtonTextActive]}>
            {isRecording ? 'Stop Recording' : 'Start Recording'}
          </Text>
        </Pressable>

        <View style={styles.statusGrid}>
          <View style={styles.statusRow}>
            <Text style={styles.label}>Connection</Text>
            <Text style={isConnected ? styles.connected : styles.disconnected}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </Text>
          </View>
          <View style={styles.statusRow}>
            <Text style={styles.label}>Recording</Text>
            <Text style={isRecording ? styles.recordingText : styles.disconnected}>
              {isRecording ? `Recording... ${elapsedSeconds} seconds` : 'Stopped'}
            </Text>
          </View>
          <Text style={styles.wakeText}>
            Native background recorder enabled. Android shows a foreground recording notification while active.
          </Text>
        </View>

        {statusMessage ? <Text style={styles.message}>{statusMessage}</Text> : null}

        {SHOW_DEBUG_PANEL && debugMessages.length > 0 ? (
          <View style={styles.debugPanel}>
            <Text style={styles.debugTitle}>WebSocket debug</Text>
            {debugMessages.map((entry) => (
              <Text key={entry} style={styles.debugText}>{entry}</Text>
            ))}
          </View>
        ) : null}
      </ScrollView>
    );
  }

  return (
    <SafeAreaView style={styles.safeArea}>
      <StatusBar style="dark" />
      {screen === 'store' ? renderStoreScreen() : null}
      {screen === 'salesperson' ? renderSalespersonScreen() : null}
      {screen === 'recording' ? renderRecordingScreen() : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safeArea: {
    flex: 1,
    backgroundColor: '#F7F4EF',
  },
  screen: {
    flexGrow: 1,
    justifyContent: 'center',
    gap: 22,
    padding: 24,
    backgroundColor: '#F7F4EF',
  },
  header: {
    alignItems: 'center',
    gap: 8,
  },
  logo: {
    color: '#A07840',
    fontSize: 34,
    fontWeight: '900',
    letterSpacing: 4,
  },
  overline: {
    color: '#A07840',
    fontSize: 12,
    fontWeight: '800',
    letterSpacing: 2,
    textTransform: 'uppercase',
  },
  title: {
    color: '#1A1614',
    fontSize: 36,
    fontWeight: '800',
    textAlign: 'center',
  },
  subheading: {
    color: '#6B6560',
    fontSize: 15,
    textAlign: 'center',
  },
  list: {
    gap: 14,
  },
  selectionButton: {
    minHeight: 74,
    justifyContent: 'center',
    borderLeftWidth: 4,
    borderLeftColor: 'transparent',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(160, 120, 64, 0.18)',
    backgroundColor: '#FFFFFF',
    padding: 16,
  },
  selectedButton: {
    borderLeftColor: '#C9A96E',
    backgroundColor: '#FFFAF2',
  },
  selectionTitle: {
    color: '#1A1614',
    fontSize: 20,
    fontWeight: '800',
  },
  selectionMeta: {
    marginTop: 5,
    color: '#6B6560',
    fontSize: 15,
  },
  backButton: {
    alignSelf: 'flex-start',
  },
  backText: {
    color: '#6B6560',
    fontSize: 15,
    fontWeight: '700',
  },
  signOutButton: {
    alignSelf: 'flex-end',
  },
  rememberedAuth: {
    gap: 10,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(201, 169, 110, 0.28)',
    backgroundColor: 'rgba(201, 169, 110, 0.11)',
    padding: 14,
    alignItems: 'center',
  },
  rememberedText: {
    color: '#A07840',
    fontWeight: '800',
  },
  pinCard: {
    gap: 14,
    borderTopWidth: 1,
    borderTopColor: 'rgba(160, 120, 64, 0.18)',
    paddingTop: 18,
  },
  setupBanner: {
    padding: 10,
    borderRadius: 12,
    backgroundColor: 'rgba(201, 169, 110, 0.11)',
    color: '#A07840',
    fontWeight: '800',
    textAlign: 'center',
  },
  stepHeading: {
    color: '#1A1614',
    fontSize: 22,
    fontWeight: '800',
    textAlign: 'center',
  },
  pinInput: {
    minHeight: 56,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(160, 120, 64, 0.24)',
    backgroundColor: '#FFFFFF',
    color: '#1A1614',
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
  },
  pinMessage: {
    minHeight: 20,
    color: '#C0392B',
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
  },
  primaryButton: {
    minHeight: 56,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#C9A96E',
    paddingHorizontal: 18,
  },
  primaryButtonText: {
    color: '#21170F',
    fontSize: 16,
    fontWeight: '800',
  },
  disabledButton: {
    opacity: 0.45,
  },
  linkText: {
    color: '#6B6560',
    fontSize: 13,
    fontWeight: '800',
    textDecorationLine: 'underline',
  },
  identityGrid: {
    gap: 10,
  },
  identityItem: {
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(160, 120, 64, 0.16)',
    backgroundColor: 'rgba(255, 255, 255, 0.78)',
    padding: 16,
  },
  label: {
    color: '#6B6560',
    fontSize: 11,
    fontWeight: '800',
    letterSpacing: 1.4,
    textTransform: 'uppercase',
  },
  identityValue: {
    marginTop: 6,
    color: '#1A1614',
    fontSize: 16,
    fontWeight: '800',
  },
  readinessMessage: {
    color: '#A07840',
    fontSize: 13,
    fontWeight: '800',
    textAlign: 'center',
  },
  interruptionBanner: {
    gap: 8,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(192, 57, 43, 0.36)',
    backgroundColor: '#FFF5F3',
    padding: 14,
  },
  interruptionTitle: {
    color: '#C0392B',
    fontSize: 15,
    fontWeight: '900',
    textAlign: 'center',
  },
  interruptionText: {
    color: '#C0392B',
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
  },
  interruptionButton: {
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
  },
  interruptionButtonText: {
    color: '#C0392B',
    fontWeight: '900',
  },
  recordButton: {
    width: 176,
    height: 176,
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    borderRadius: 88,
    borderWidth: 8,
    borderColor: 'rgba(201, 169, 110, 0.45)',
    backgroundColor: '#C9A96E',
  },
  recordButtonActive: {
    borderColor: 'rgba(192, 57, 43, 0.36)',
    backgroundColor: '#FFF5F3',
  },
  recordIcon: {
    width: 34,
    height: 34,
    borderRadius: 18,
    borderWidth: 3,
    borderBottomWidth: 7,
    borderColor: '#21170F',
  },
  stopIcon: {
    width: 30,
    height: 30,
    borderRadius: 7,
    backgroundColor: '#C0392B',
  },
  recordButtonText: {
    color: '#21170F',
    fontWeight: '900',
  },
  recordButtonTextActive: {
    color: '#C0392B',
  },
  statusGrid: {
    gap: 12,
  },
  statusRow: {
    gap: 6,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(160, 120, 64, 0.16)',
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
    padding: 16,
  },
  connected: {
    color: '#2D7A4F',
    fontWeight: '800',
  },
  disconnected: {
    color: '#6B6560',
    fontWeight: '800',
  },
  recordingText: {
    color: '#A07840',
    fontWeight: '800',
  },
  wakeText: {
    color: '#6B6560',
    fontSize: 11,
    lineHeight: 16,
    textAlign: 'center',
  },
  message: {
    color: '#6B6560',
    fontSize: 14,
    lineHeight: 20,
    textAlign: 'center',
  },
  debugPanel: {
    gap: 8,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(160, 120, 64, 0.18)',
    backgroundColor: '#FFFFFF',
    padding: 12,
  },
  debugTitle: {
    color: '#1A1614',
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  debugText: {
    color: '#6B6560',
    fontSize: 11,
    lineHeight: 15,
  },
});
