/**
 * ============================================================================
 * ANALIZADOR TÁCTICO — ENGINE DEL MOCKUP INTERACTIVO DE ALTA FIDELIDAD
 * ============================================================================
 * Lógica vanilla JS sin dependencias.
 * Sincronización en tiempo real entre:
 *   1. Canvas de Video Simulado (proyección broadcast con bounding boxes y tracks)
 *   2. Canvas de Cancha 2D Cenital (105m x 68m con envolvente convexa y centroides)
 *   3. Panel de métricas de bloque recalculadas en vivo
 *   4. Tagueo one-click con buffer de -10s y timeline interactivo
 *   5. Inspector táctico individual de jugadores
 *   6. Semáforo post-partido interactivo con exportación de reporte
 * ============================================================================
 */

(function () {
  "use strict";

  // --------------------------------------------------------------------------
  // 1. ESTADO GLOBAL DE LA APLICACIÓN
  // --------------------------------------------------------------------------
  const MATCH_DATA = {
    name: "Sportivo Belgrano vs. Alumni",
    duration: 2700.0, // 45:00 minutos de primer tiempo
    currentTime: 860.0, // Instante inicial: 14:20 (momento táctico clave)
    isPlaying: false,
    playbackSpeed: 1.0,
    activeView: "tactica", // 'tactica' | 'jugadores' | 'patrones' | 'semaforo'
    selectedPlayerId: "home_8", // Por defecto: Rodrigo Fernández (#8)
    selectedTeam: "home",
    selectedZoneFilter: "all",
    selectedSevFilter: "all",
    highlightTrack: null, // Track resaltado al saltar desde un patrón táctico
    highlightTimer: null
  };

  // Plantel de Sportivo Belgrano (Local - Azul #1f77b4)
  const HOME_ROSTER = [
    { id: "home_1", number: 1, name: "Matías Benítez", role: "Arquero", zone: "arquero", min: 90, dist: 4650, maxSpd: 21.4, avgSpd: 4.8, sprints: 4, rating: "green", posX: 7.5, posY: 34.0, note: "Seguro en balones aéreos y juego con los pies en salida." },
    { id: "home_4", number: 4, name: "Lucas Rossi", role: "Lateral Derecho", zone: "defensa", min: 90, dist: 10240, maxSpd: 29.8, avgSpd: 7.1, sprints: 24, rating: "red", posX: 36.0, posY: 56.5, note: "Desajustes posicionales en la línea. Deja espacio a su espalda en transiciones." },
    { id: "home_2", number: 2, name: "Julián Maidana", role: "Primer Central", zone: "defensa", min: 90, dist: 8920, maxSpd: 27.2, avgSpd: 6.4, sprints: 12, rating: "yellow", posX: 26.5, posY: 42.0, note: "Firme en el 1v1; demora en achicar cuando el mediocampo presiona arriba." },
    { id: "home_6", number: 6, name: "Facundo Albarracín", role: "Segundo Central", zone: "defensa", min: 90, dist: 9140, maxSpd: 27.8, avgSpd: 6.5, sprints: 14, rating: "green", posX: 27.0, posY: 26.0, note: "Excelente lectura en los cruces de cobertura. Salida limpia." },
    { id: "home_3", number: 3, name: "Esteban Mansilla", role: "Lateral Izquierdo", zone: "defensa", min: 90, dist: 10450, maxSpd: 29.4, avgSpd: 7.2, sprints: 22, rating: "green", posX: 37.5, posY: 11.5, note: "Gran ida y vuelta por la banda. Cerró bien el carril interno." },
    { id: "home_5", number: 5, name: "Matías Kranevitter", role: "Mediocentro Posicional", zone: "mediocampo", min: 90, dist: 11200, maxSpd: 28.1, avgSpd: 7.5, sprints: 18, rating: "green", posX: 46.0, posY: 34.0, note: "Eje del equipo. Recuperó 11 balones en campo propio y distribuyó con criterio." },
    { id: "home_8", number: 8, name: "Rodrigo Fernández", role: "Interior Derecho", zone: "mediocampo", min: 82, dist: 10180, maxSpd: 29.2, avgSpd: 7.3, sprints: 26, rating: "green", posX: 58.2, posY: 46.5, note: "Gran despliegue ofensivo; ajustar repliegue hacia el doble 5 al perder posesión." },
    { id: "home_10", number: 10, name: "Franco Vázquez", role: "Interior Izquierdo / Enlace", zone: "mediocampo", min: 78, dist: 9680, maxSpd: 28.5, avgSpd: 6.9, sprints: 19, rating: "green", posX: 59.5, posY: 22.0, note: "Generador de juego principal. 3 pases clave entre líneas." },
    { id: "home_7", number: 7, name: "Nicolás Gómez", role: "Extremo Derecho", zone: "ataque", min: 90, dist: 10890, maxSpd: 31.8, avgSpd: 7.4, sprints: 34, rating: "yellow", posX: 74.0, posY: 57.0, note: "Pico de velocidad del partido (31.8 km/h). Le faltó culminación en el último tercio." },
    { id: "home_9", number: 9, name: "Gabriel Scocco", role: "Centrodelantero", zone: "ataque", min: 90, dist: 9350, maxSpd: 28.9, avgSpd: 6.6, sprints: 21, rating: "green", posX: 76.5, posY: 34.0, note: "Autor del segundo gol. Presionó la salida de los centrales rivales sin descanso." },
    { id: "home_11", number: 11, name: "Juan Cavallaro", role: "Extremo Izquierdo", zone: "ataque", min: 65, dist: 7840, maxSpd: 30.4, avgSpd: 7.1, sprints: 25, rating: "green", posX: 73.5, posY: 11.0, note: "Desequilibrio constante en el mano a mano; desgastó al lateral rival." },
    // Suplentes
    { id: "home_14", number: 14, name: "Braian Toledo", role: "Lateral Relevo", zone: "defensa", min: 25, dist: 3100, maxSpd: 28.0, avgSpd: 7.0, sprints: 8, rating: "green", posX: 38.0, posY: 12.0, note: "Entró con solidez para cerrar el partido." },
    { id: "home_16", number: 16, name: "Mauricio Sosa", role: "Volante Mixto", zone: "mediocampo", min: 12, dist: 1720, maxSpd: 27.4, avgSpd: 6.8, sprints: 5, rating: "yellow", posX: 52.0, posY: 33.0, note: "Poco tiempo en cancha; aportó orden en la contención." }
  ];

  // Plantel de Alumni (Visitante - Rojo #d62728)
  const AWAY_ROSTER = [
    { id: "away_1", number: 1, name: "Carlos López", role: "Arquero", zone: "arquero", min: 90, dist: 4800, maxSpd: 20.8, avgSpd: 4.7, sprints: 3, rating: "green", posX: 97.5, posY: 34.0, note: "Evitó una diferencia mayor en el primer tiempo." },
    { id: "away_4", number: 4, name: "Santiago Barboza", role: "Lateral Derecho", zone: "defensa", min: 90, dist: 9850, maxSpd: 28.6, avgSpd: 6.9, sprints: 18, rating: "yellow", posX: 68.0, posY: 57.0, note: "Sufrió con las subidas del extremo izquierdo." },
    { id: "away_2", number: 2, name: "Federico Pereyra", role: "Primer Central", zone: "defensa", min: 90, dist: 8900, maxSpd: 26.5, avgSpd: 6.3, sprints: 11, rating: "green", posX: 78.0, posY: 42.0, note: "Ganó la mayoría de los duelos aéreos." },
    { id: "away_6", number: 6, name: "Germán Rivero", role: "Segundo Central", zone: "defensa", min: 90, dist: 8750, maxSpd: 26.8, avgSpd: 6.2, sprints: 10, rating: "yellow", posX: 78.5, posY: 26.0, note: "Complicado ante la movilidad del delantero centro." },
    { id: "away_3", number: 3, name: "Facundo Carrizo", role: "Lateral Izquierdo", zone: "defensa", min: 90, dist: 9940, maxSpd: 28.4, avgSpd: 6.8, sprints: 17, rating: "yellow", posX: 67.5, posY: 11.0, note: "Tardanza recurrente en la basculación hacia el balón." },
    { id: "away_8", number: 8, name: "Lucas Biglia", role: "Volante Derecho", zone: "mediocampo", min: 75, dist: 8700, maxSpd: 29.1, avgSpd: 7.0, sprints: 20, rating: "green", posX: 54.0, posY: 55.0, note: "Autor del gol de Alumni. Buen remate de media distancia." },
    { id: "away_5", number: 5, name: "Diego Villar", role: "Mediocentro 1", zone: "mediocampo", min: 90, dist: 10800, maxSpd: 27.6, avgSpd: 7.2, sprints: 15, rating: "yellow", posX: 57.0, posY: 40.0, note: "Desbordado por momentos ante la superioridad 3v2 del medio rival." },
    { id: "away_7", number: 7, name: "Ignacio Malcorra", role: "Mediocentro 2", zone: "mediocampo", min: 90, dist: 10650, maxSpd: 28.0, avgSpd: 7.1, sprints: 16, rating: "yellow", posX: 57.5, posY: 28.0, note: "Correcto en salida, pero con poco repliegue." },
    { id: "away_11", number: 11, name: "Agustín Allione", role: "Volante Izquierdo", zone: "mediocampo", min: 80, dist: 9400, maxSpd: 29.5, avgSpd: 7.0, sprints: 22, rating: "green", posX: 53.5, posY: 12.0, note: "Generó peligro cada vez que encaró en velocidad." },
    { id: "away_9", number: 9, name: "Mauro Matos", role: "Delantero de Área", zone: "ataque", min: 90, dist: 8900, maxSpd: 27.0, avgSpd: 6.2, sprints: 14, rating: "yellow", posX: 34.0, posY: 39.0, note: "Poco abastecido durante la mayor parte del cotejo." },
    { id: "away_10", number: 10, name: "César Pereyra", role: "Segunda Punta", zone: "ataque", min: 85, dist: 9600, maxSpd: 29.8, avgSpd: 6.8, sprints: 23, rating: "green", posX: 36.0, posY: 27.0, note: "Activo flotando a la espalda del mediocentro local." }
  ];

  // Historial de eventos tagueados (precargado con jugadas clave del partido)
  let taggedEvents = [
    { id: 1, time: 245.0, type: "Presión", team: "home", label: "Presión Alta Coordinada", note: "Recuperación en 3/4 tras saque de arco rival." },
    { id: 2, time: 495.0, type: "Pérdida", team: "home", label: "Desajuste Lateral Derecho", note: "Rossi pierde la espalda, Alumni avanza con ventaja." },
    { id: 3, time: 665.0, type: "Transición", team: "home", label: "Contragolpe Rápido", note: "Pase en profundidad de Vázquez a Gómez." },
    { id: 4, time: 860.0, type: "Salida", team: "home", label: "Salida de Fondo 2-3-2", note: "Kranevitter se incrusta entre centrales para salir limpio." },
    { id: 5, time: 1160.0, type: "Pelota Parada", team: "away", label: "Córner Visitante", note: "Centro peligroso al segundo palo defendido por Benítez." }
  ];

  // --------------------------------------------------------------------------
  // 2. ELEMENTOS DEL DOM
  // --------------------------------------------------------------------------
  const DOM = {
    // Header
    headerClock: document.getElementById("headerClock"),
    btnQuickReport: document.getElementById("btnQuickReport"),
    navButtons: document.querySelectorAll(".nav-btn"),
    viewContainers: document.querySelectorAll(".view-container"),

    // Mesa Táctica
    screensWrapper: document.getElementById("screensWrapper"),
    modeButtons: document.querySelectorAll(".mode-btn"),
    chkShowHull: document.getElementById("chkShowHull"),
    chkShowCentroid: document.getElementById("chkShowCentroid"),
    chkShowVectors: document.getElementById("chkShowVectors"),
    videoCanvas: document.getElementById("videoCanvas"),
    pitchCanvas: document.getElementById("pitchCanvas"),
    hudTrackCount: document.getElementById("hudTrackCount"),

    // Controles de Reproducción
    btnPlayPause: document.getElementById("btnPlayPause"),
    iconPlay: document.getElementById("iconPlay"),
    iconPause: document.getElementById("iconPause"),
    btnStepBack: document.getElementById("btnStepBack"),
    btnStepForward: document.getElementById("btnStepForward"),
    speedButtons: document.querySelectorAll(".speed-btn"),
    currentTimeDisplay: document.getElementById("currentTimeDisplay"),
    totalTimeDisplay: document.getElementById("totalTimeDisplay"),
    scrubberTrack: document.getElementById("scrubberTrack"),
    scrubberProgress: document.getElementById("scrubberProgress"),
    scrubberPlayhead: document.getElementById("scrubberPlayhead"),
    timelineMarkers: document.getElementById("timelineMarkers"),

    // Métricas en Vivo
    localAmplitud: document.getElementById("localAmplitud"),
    localProfundidad: document.getElementById("localProfundidad"),
    localArea: document.getElementById("localArea"),
    localCompacidad: document.getElementById("localCompacidad"),
    fillLocalAmp: document.getElementById("fillLocalAmp"),
    fillLocalProf: document.getElementById("fillLocalProf"),
    fillLocalArea: document.getElementById("fillLocalArea"),
    fillLocalComp: document.getElementById("fillLocalComp"),

    awayAmplitud: document.getElementById("awayAmplitud"),
    awayProfundidad: document.getElementById("awayProfundidad"),
    awayArea: document.getElementById("awayArea"),
    awayCompacidad: document.getElementById("awayCompacidad"),
    fillAwayAmp: document.getElementById("fillAwayAmp"),
    fillAwayProf: document.getElementById("fillAwayProf"),
    fillAwayArea: document.getElementById("fillAwayArea"),
    fillAwayComp: document.getElementById("fillAwayComp"),

    // Tagueo
    tagButtons: document.querySelectorAll(".tag-btn"),
    taggedEventsList: document.getElementById("taggedEventsList"),
    tagCount: document.getElementById("tagCount"),

    // Vista Jugadores
    teamFilterBtns: document.querySelectorAll(".team-filter-btn"),
    zonePills: document.querySelectorAll(".zone-pill"),
    playerSearchInput: document.getElementById("playerSearchInput"),
    playersTableBody: document.getElementById("playersTableBody"),
    tableHeaders: document.querySelectorAll(".analytics-table th"),
    inspectNum: document.getElementById("inspectNum"),
    inspectName: document.getElementById("inspectName"),
    inspectRole: document.getElementById("inspectRole"),
    inspectRatingPill: document.getElementById("inspectRatingPill"),
    inspectorPitchCanvas: document.getElementById("inspectorPitchCanvas"),
    centroidCoordinate: document.getElementById("centroidCoordinate"),
    fillWalk: document.getElementById("fillWalk"),
    fillJog: document.getElementById("fillJog"),
    fillRun: document.getElementById("fillRun"),
    fillSprint: document.getElementById("fillSprint"),
    valWalk: document.getElementById("valWalk"),
    valJog: document.getElementById("valJog"),
    valRun: document.getElementById("valRun"),
    valSprint: document.getElementById("valSprint"),
    inspectDtNotes: document.getElementById("inspectDtNotes"),
    btnJumpPlayerVideo: document.getElementById("btnJumpPlayerVideo"),

    // Vista Patrones
    sevPills: document.querySelectorAll(".sev-pill"),
    patternsGrid: document.getElementById("patternsGrid"),

    // Vista Semáforo
    semaforoRosterGrid: document.getElementById("semaforoRosterGrid"),
    countVerde: document.getElementById("countVerde"),
    countAmarillo: document.getElementById("countAmarillo"),
    countRojo: document.getElementById("countRojo"),
    pctVerde: document.getElementById("pctVerde"),
    pctAmarillo: document.getElementById("pctAmarillo"),
    pctRojo: document.getElementById("pctRojo"),
    btnExportWhatsApp: document.getElementById("btnExportWhatsApp"),
    btnResetSemaforo: document.getElementById("btnResetSemaforo"),

    // Modal & Toast
    reportModal: document.getElementById("reportModal"),
    reportTextarea: document.getElementById("reportTextarea"),
    btnCloseModal: document.getElementById("btnCloseModal"),
    btnCopyReport: document.getElementById("btnCopyReport"),
    copyStatusMsg: document.getElementById("copyStatusMsg"),
    toastNotification: document.getElementById("toastNotification"),
    toastMessage: document.getElementById("toastMessage")
  };

  // --------------------------------------------------------------------------
  // 3. HELPERS DE FORMATO Y GEOMETRÍA
  // --------------------------------------------------------------------------
  function formatTime(sec, showTenths = true) {
    const s = Math.max(0, sec);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    const wholeSec = Math.floor(rem);
    const tenths = Math.floor((rem - wholeSec) * 10);
    const mm = String(m).padStart(2, "0");
    const ss = String(wholeSec).padStart(2, "0");
    return showTenths ? `${mm}:${ss}.${tenths}` : `${mm}:${ss}`;
  }

  function showToast(msg) {
    DOM.toastMessage.textContent = msg;
    DOM.toastNotification.classList.remove("hidden");
    clearTimeout(DOM.toastNotification._timer);
    DOM.toastNotification._timer = setTimeout(() => {
      DOM.toastNotification.classList.add("hidden");
    }, 2800);
  }

  // Envolvente convexa (Algoritmo Andrew Monotone Chain)
  function computeConvexHull(points) {
    if (points.length < 3) return points;
    const sorted = points.slice().sort((a, b) => a[0] === b[0] ? a[1] - b[1] : a[0] - b[0]);
    const lower = [];
    for (let p of sorted) {
      while (lower.length >= 2 && crossProduct(lower[lower.length - 2], lower[lower.length - 1], p) <= 0) {
        lower.pop();
      }
      lower.push(p);
    }
    const upper = [];
    for (let i = sorted.length - 1; i >= 0; i--) {
      const p = sorted[i];
      while (upper.length >= 2 && crossProduct(upper[upper.length - 2], upper[upper.length - 1], p) <= 0) {
        upper.pop();
      }
      upper.push(p);
    }
    lower.pop();
    upper.pop();
    return lower.concat(upper);
  }

  function crossProduct(o, a, b) {
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  }

  function polygonArea(hull) {
    if (hull.length < 3) return 0;
    let area = 0;
    for (let i = 0; i < hull.length; i++) {
      const j = (i + 1) % hull.length;
      area += hull[i][0] * hull[j][1];
      area -= hull[j][0] * hull[i][1];
    }
    return Math.abs(area) / 2.0;
  }

  // --------------------------------------------------------------------------
  // 4. GENERADOR DINÁMICO DE POSICIONES (SIMULACIÓN MATEMÁTICA REALISTA)
  // --------------------------------------------------------------------------
  /**
   * Calcula las posiciones exactas de todos los jugadores en la cancha (105m x 68m)
   * para un segundo determinado t, produciendo desplazamientos tácticos armónicos.
   */
  function getPlayersAtTime(t) {
    const timeRatio = t / 60.0; // Ciclos por minuto
    
    // Movimiento de la pelota (simula posesión y cambios de frente)
    const ballWave = Math.sin(timeRatio * 1.8);
    const ballWaveY = Math.cos(timeRatio * 2.4);
    const ballX = 52.5 + ballWave * 26.0 + Math.sin(t * 0.4) * 8.0;
    const ballY = 34.0 + ballWaveY * 20.0 + Math.cos(t * 0.5) * 6.0;

    // Desplazamiento del bloque según dónde está la pelota
    const blockShiftX = (ballX - 52.5) * 0.35;
    const blockShiftY = (ballY - 34.0) * 0.28;

    // Local (Ataque hacia la derecha -> X+)
    const homePlayers = HOME_ROSTER.map((p) => {
      let isGk = p.zone === "arquero";
      // Desplazamiento individual armónico
      let dx = Math.sin(t * 0.8 + p.number * 1.5) * (isGk ? 1.5 : 4.0);
      let dy = Math.cos(t * 0.7 + p.number * 1.2) * (isGk ? 3.0 : 5.0);

      // Basculación de equipo
      let px = p.posX + (isGk ? 0 : blockShiftX) + dx;
      let py = p.posY + (isGk ? dy * 0.4 : blockShiftY) + dy;

      // Anomalía táctica forzada para #4 Lucas Rossi (desconexión defensiva sostenida)
      if (p.number === 4) {
        px += 8.5 + Math.sin(t * 0.5) * 3.0; // Queda desfasado hacia adelante
        py += 4.0;
      }

      // Confinar a límites de cancha
      px = Math.max(1.5, Math.min(103.5, px));
      py = Math.max(1.5, Math.min(66.5, py));

      // Vector de velocidad
      const vx = Math.cos(t * 1.1 + p.number) * 3.2;
      const vy = Math.sin(t * 1.1 + p.number) * 2.8;

      return {
        id: p.id,
        trackId: p.number,
        number: p.number,
        name: p.name,
        role: p.role,
        zone: p.zone,
        team: "home",
        x: px,
        y: py,
        vx: vx,
        vy: vy
      };
    });

    // Visitante (Ataque hacia la izquierda -> X-)
    const awayPlayers = AWAY_ROSTER.map((p) => {
      let isGk = p.zone === "arquero";
      let dx = Math.sin(t * 0.75 + p.number * 1.3) * (isGk ? 1.5 : 4.2);
      let dy = Math.cos(t * 0.85 + p.number * 1.1) * (isGk ? 3.0 : 5.2);

      let px = p.posX + (isGk ? 0 : blockShiftX * 0.9) + dx;
      let py = p.posY + (isGk ? dy * 0.4 : blockShiftY * 0.9) + dy;

      // Anomalía táctica forzada para Alumni: Bloque estirado en transiciones
      if (p.zone === "ataque") {
        px -= 6.0; // Delanteros quedan muy arriba
      } else if (p.zone === "defensa") {
        px += 4.0; // Defensores quedan clavados atrás
      }

      px = Math.max(1.5, Math.min(103.5, px));
      py = Math.max(1.5, Math.min(66.5, py));

      const vx = -Math.cos(t * 0.9 + p.number) * 2.9;
      const vy = -Math.sin(t * 0.9 + p.number) * 2.5;

      return {
        id: p.id,
        trackId: 20 + p.number,
        number: p.number,
        name: p.name,
        role: p.role,
        zone: p.zone,
        team: "away",
        x: px,
        y: py,
        vx: vx,
        vy: vy
      };
    });

    return {
      home: homePlayers,
      away: awayPlayers,
      ball: { x: ballX, y: ballY, z: 0.1 }
    };
  }

  // --------------------------------------------------------------------------
  // 5. RENDERER DE CANCHA 2D CENITAL (105m x 68m)
  // --------------------------------------------------------------------------
  function drawPitch(ctx, width, height, data, options = {}) {
    const W = width;
    const H = height;
    ctx.clearRect(0, 0, W, H);

    // Fondo Césped oscuro estilo cabina analítica
    const stripeCount = 10;
    const stripeW = W / stripeCount;
    for (let i = 0; i < stripeCount; i++) {
      ctx.fillStyle = i % 2 === 0 ? "#14331e" : "#173b23";
      ctx.fillRect(i * stripeW, 0, stripeW, H);
    }

    // Escala métrica (0..105 -> 0..W, 0..68 -> 0..H)
    const sx = (mx) => (mx / 105.0) * W;
    const sy = (my) => (my / 68.0) * H;

    // Dibujo de líneas reglamentarias
    ctx.strokeStyle = "rgba(255, 255, 255, 0.75)";
    ctx.lineWidth = 1.5;

    // Perímetro exterior
    ctx.strokeRect(sx(0), sy(0), sx(105), sy(68));

    // Línea de mitad de campo
    ctx.beginPath();
    ctx.moveTo(sx(52.5), sy(0));
    ctx.lineTo(sx(52.5), sy(68));
    ctx.stroke();

    // Círculo central (radio 9.15m)
    ctx.beginPath();
    ctx.ellipse(sx(52.5), sy(34.0), (9.15 / 105.0) * W, (9.15 / 68.0) * H, 0, 0, Math.PI * 2);
    ctx.stroke();

    // Punto central
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(sx(52.5), sy(34.0), 3, 0, Math.PI * 2);
    ctx.fill();

    // Áreas de penalti (16.5m x 40.3m, origen y=13.85 a 54.15)
    // Arco izquierdo (Local defiende)
    ctx.strokeRect(sx(0), sy(13.85), sx(16.5), sy(40.3));
    ctx.strokeRect(sx(0), sy(24.85), sx(5.5), sy(18.3)); // Área chica
    // Punto de penal
    ctx.beginPath();
    ctx.arc(sx(11.0), sy(34.0), 2.5, 0, Math.PI * 2);
    ctx.fill();
    // Medialuna
    ctx.beginPath();
    ctx.arc(sx(11.0), sy(34.0), (9.15 / 105.0) * W, -0.9, 0.9);
    ctx.stroke();

    // Arco derecho (Visitante defiende)
    ctx.strokeRect(sx(105 - 16.5), sy(13.85), sx(16.5), sy(40.3));
    ctx.strokeRect(sx(105 - 5.5), sy(24.85), sx(5.5), sy(18.3)); // Área chica
    // Punto de penal
    ctx.beginPath();
    ctx.arc(sx(105 - 11.0), sy(34.0), 2.5, 0, Math.PI * 2);
    ctx.fill();
    // Medialuna
    ctx.beginPath();
    ctx.arc(sx(105 - 11.0), sy(34.0), (9.15 / 105.0) * W, Math.PI - 0.9, Math.PI + 0.9);
    ctx.stroke();

    // Arcos de esquina
    const cornerR = (1.0 / 105.0) * W * 1.5;
    ctx.beginPath(); ctx.arc(sx(0), sy(0), cornerR, 0, Math.PI / 2); ctx.stroke();
    ctx.beginPath(); ctx.arc(sx(0), sy(68), cornerR, -Math.PI / 2, 0); ctx.stroke();
    ctx.beginPath(); ctx.arc(sx(105), sy(0), cornerR, Math.PI / 2, Math.PI); ctx.stroke();
    ctx.beginPath(); ctx.arc(sx(105), sy(68), cornerR, Math.PI, -Math.PI / 2); ctx.stroke();

    if (!data) return;

    // 1. Envolventes Convexas (Bloques de Equipo)
    if (options.showHull !== false) {
      // Hull Local (Azul)
      const homeFieldPts = data.home.filter((p) => p.zone !== "arquero").map((p) => [p.x, p.y]);
      const homeHull = computeConvexHull(homeFieldPts);
      if (homeHull.length >= 3) {
        ctx.beginPath();
        ctx.moveTo(sx(homeHull[0][0]), sy(homeHull[0][1]));
        for (let i = 1; i < homeHull.length; i++) {
          ctx.lineTo(sx(homeHull[i][0]), sy(homeHull[i][1]));
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(31, 119, 180, 0.16)";
        ctx.fill();
        ctx.strokeStyle = "rgba(56, 189, 248, 0.55)";
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Hull Visitante (Rojo)
      const awayFieldPts = data.away.filter((p) => p.zone !== "arquero").map((p) => [p.x, p.y]);
      const awayHull = computeConvexHull(awayFieldPts);
      if (awayHull.length >= 3) {
        ctx.beginPath();
        ctx.moveTo(sx(awayHull[0][0]), sy(awayHull[0][1]));
        for (let i = 1; i < awayHull.length; i++) {
          ctx.lineTo(sx(awayHull[i][0]), sy(awayHull[i][1]));
        }
        ctx.closePath();
        ctx.fillStyle = "rgba(214, 39, 40, 0.16)";
        ctx.fill();
        ctx.strokeStyle = "rgba(248, 113, 113, 0.55)";
        ctx.lineWidth = 1.2;
        ctx.setLineDash([4, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // 2. Centroides y Líneas Defensivas
    if (options.showCentroid !== false) {
      const homeField = data.home.filter((p) => p.zone !== "arquero");
      const awayField = data.away.filter((p) => p.zone !== "arquero");

      if (homeField.length > 0) {
        const hcx = homeField.reduce((acc, p) => acc + p.x, 0) / homeField.length;
        const hcy = homeField.reduce((acc, p) => acc + p.y, 0) / homeField.length;

        // Rombo centroide
        ctx.fillStyle = "#38bdf8";
        ctx.beginPath();
        const cr = 5;
        ctx.moveTo(sx(hcx), sy(hcy) - cr);
        ctx.lineTo(sx(hcx) + cr, sy(hcy));
        ctx.lineTo(sx(hcx), sy(hcy) + cr);
        ctx.lineTo(sx(hcx) - cr, sy(hcy));
        ctx.closePath();
        ctx.fill();

        // Línea defensiva (último central)
        const defXs = data.home.filter((p) => p.zone === "defensa").map((p) => p.x);
        const minDefX = Math.min(...defXs);
        ctx.strokeStyle = "rgba(56, 189, 248, 0.4)";
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        ctx.moveTo(sx(minDefX), sy(6));
        ctx.lineTo(sx(minDefX), sy(62));
        ctx.stroke();
        ctx.setLineDash([]);
      }

      if (awayField.length > 0) {
        const acx = awayField.reduce((acc, p) => acc + p.x, 0) / awayField.length;
        const acy = awayField.reduce((acc, p) => acc + p.y, 0) / awayField.length;

        ctx.fillStyle = "#f87171";
        ctx.beginPath();
        const cr = 5;
        ctx.moveTo(sx(acx), sy(acy) - cr);
        ctx.lineTo(sx(acx) + cr, sy(acy));
        ctx.lineTo(sx(acx), sy(acy) + cr);
        ctx.lineTo(sx(acx) - cr, sy(acy));
        ctx.closePath();
        ctx.fill();

        const defXs = data.away.filter((p) => p.zone === "defensa").map((p) => p.x);
        const maxDefX = Math.max(...defXs);
        ctx.strokeStyle = "rgba(248, 113, 113, 0.4)";
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 3]);
        ctx.beginPath();
        ctx.moveTo(sx(maxDefX), sy(6));
        ctx.lineTo(sx(maxDefX), sy(62));
        ctx.stroke();
        ctx.setLineDash([]);
      }
    }

    // 3. Jugadores (Local & Visitante)
    const drawPlayerDot = (p, teamColor, lightColor) => {
      const px = sx(p.x);
      const py = sy(p.y);
      const radius = 9;

      // Vectores de velocidad
      if (options.showVectors !== false && (p.vx || p.vy)) {
        ctx.strokeStyle = "rgba(255, 255, 255, 0.6)";
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.moveTo(px, py);
        ctx.lineTo(px + p.vx * 3.5, py + p.vy * 3.5);
        ctx.stroke();
      }

      // Anillo de realce si es el jugador seleccionado o con alerta
      if (MATCH_DATA.selectedPlayerId === p.id || MATCH_DATA.highlightTrack === p.number) {
        ctx.strokeStyle = "#c3ff00";
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.arc(px, py, radius + 4, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Círculo principal
      ctx.fillStyle = teamColor;
      ctx.beginPath();
      ctx.arc(px, py, radius, 0, Math.PI * 2);
      ctx.fill();

      // Borde
      ctx.strokeStyle = lightColor;
      ctx.lineWidth = 1.5;
      ctx.stroke();

      // Dorsal
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 8px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(p.number, px, py + 0.5);
    };

    // Dibujar todos los locales
    data.home.forEach((p) => drawPlayerDot(p, "#1f77b4", "#38bdf8"));

    // Dibujar todos los visitantes
    data.away.forEach((p) => drawPlayerDot(p, "#d62728", "#f87171"));

    // 4. Balón con halo
    if (data.ball) {
      const bx = sx(data.ball.x);
      const by = sy(data.ball.y);
      ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
      ctx.beginPath();
      ctx.arc(bx, by, 7, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(bx, by, 4.5, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = "#000000";
      ctx.lineWidth = 1;
      ctx.stroke();
    }
  }

  // --------------------------------------------------------------------------
  // 6. RENDERER DE VIDEO SIMULADO CON INFERENCIA DE TRACKING
  // --------------------------------------------------------------------------
  function drawVideo(ctx, width, height, data) {
    const W = width;
    const H = height;
    ctx.clearRect(0, 0, W, H);

    // Fondo: Gradiente de césped en perspectiva broadcast
    const grad = ctx.createLinearGradient(0, 0, 0, H);
    grad.addColorStop(0, "#194225");
    grad.addColorStop(1, "#12301a");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, W, H);

    // Líneas de cancha en perspectiva
    ctx.strokeStyle = "rgba(255, 255, 255, 0.45)";
    ctx.lineWidth = 2;

    // Línea lateral inferior
    ctx.beginPath();
    ctx.moveTo(W * 0.05, H * 0.88);
    ctx.lineTo(W * 0.95, H * 0.88);
    ctx.stroke();

    // Línea lateral superior (más lejana)
    ctx.beginPath();
    ctx.moveTo(W * 0.15, H * 0.22);
    ctx.lineTo(W * 0.85, H * 0.22);
    ctx.stroke();

    // Línea de mitad de cancha oblicua
    ctx.beginPath();
    ctx.moveTo(W * 0.50, H * 0.22);
    ctx.lineTo(W * 0.50, H * 0.88);
    ctx.stroke();

    // Círculo central elíptico en perspectiva
    ctx.beginPath();
    ctx.ellipse(W * 0.50, H * 0.55, W * 0.12, H * 0.14, 0, 0, Math.PI * 2);
    ctx.stroke();

    if (!data) return;

    // Función de mapeo de coordenadas cenitales (0..105, 0..68) a pantalla perspectiva (W, H)
    const mapToScreen = (mx, my) => {
      const normX = mx / 105.0;
      const normY = my / 68.0;

      // Profundidad en perspectiva: Y=0 está arriba (lejos), Y=68 está abajo (cerca)
      const perspY = 0.22 + normY * 0.66;
      const widthScale = 0.70 + normY * 0.30;
      const perspX = (0.5 + (normX - 0.5) * widthScale) * W;
      const screenY = perspY * H;

      return { x: perspX, y: screenY, scale: 0.65 + normY * 0.55 };
    };

    // Dibujar cajas de detección y tracking (Bounding Boxes)
    const allPlayers = [...data.home, ...data.away].sort((a, b) => a.y - b.y);

    allPlayers.forEach((p) => {
      const scr = mapToScreen(p.x, p.y);
      const isHome = p.team === "home";
      const boxW = 20 * scr.scale;
      const boxH = 44 * scr.scale;
      const boxX = scr.x - boxW / 2;
      const boxY = scr.y - boxH;

      const teamColor = isHome ? "#38bdf8" : "#f87171";
      const teamBg = isHome ? "rgba(31, 119, 180, 0.2)" : "rgba(214, 39, 40, 0.2)";

      // Bounding box translúcida
      ctx.fillStyle = teamBg;
      ctx.fillRect(boxX, boxY, boxW, boxH);

      // Borde de la caja
      ctx.strokeStyle = teamColor;
      ctx.lineWidth = 1.4;
      ctx.strokeRect(boxX, boxY, boxW, boxH);

      // Etiqueta superior del tracker
      const tagText = `${isHome ? "LOC" : "VIS"} #${p.number}`;
      ctx.fillStyle = "rgba(10, 11, 13, 0.85)";
      ctx.fillRect(boxX, boxY - 14, boxW + 20, 13);
      ctx.fillStyle = teamColor;
      ctx.font = "bold 9px ui-monospace, monospace";
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(tagText, boxX + 2, boxY - 7.5);

      // Punto en los pies (proyección homográfica)
      ctx.fillStyle = "#ffffff";
      ctx.beginPath();
      ctx.arc(scr.x, scr.y, 2.5, 0, Math.PI * 2);
      ctx.fill();
    });

    // Bounding box de la pelota
    if (data.ball) {
      const bscr = mapToScreen(data.ball.x, data.ball.y);
      const bsize = 12 * bscr.scale;
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(bscr.x - bsize / 2, bscr.y - bsize / 2, bsize, bsize);

      ctx.fillStyle = "rgba(0, 0, 0, 0.85)";
      ctx.fillRect(bscr.x - 14, bscr.y - bsize / 2 - 12, 28, 11);
      ctx.fillStyle = "#ffffff";
      ctx.font = "bold 8.5px ui-monospace, monospace";
      ctx.textAlign = "center";
      ctx.fillText("BALL", bscr.x, bscr.y - bsize / 2 - 6.5);
    }
  }

  // --------------------------------------------------------------------------
  // 7. CÁLCULO DE MÉTRICAS DE BLOQUE EN VIVO
  // --------------------------------------------------------------------------
  function updateBlockMetrics(data) {
    const calcTeam = (players) => {
      const field = players.filter((p) => p.zone !== "arquero");
      if (field.length < 3) return { amp: 35.0, prof: 25.0, area: 800, comp: 12.0 };

      const xs = field.map((p) => p.x);
      const ys = field.map((p) => p.y);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);

      const amp = maxY - minY; // Ancho lateral
      const prof = maxX - minX; // Largo arco-arco

      const hull = computeConvexHull(field.map((p) => [p.x, p.y]));
      const area = polygonArea(hull);

      const cx = xs.reduce((a, b) => a + b, 0) / field.length;
      const cy = ys.reduce((a, b) => a + b, 0) / field.length;
      const comp = field.reduce((acc, p) => acc + Math.hypot(p.x - cx, p.y - cy), 0) / field.length;

      return { amp, prof, area, comp };
    };

    const homeM = calcTeam(data.home);
    const awayM = calcTeam(data.away);

    // Actualizar DOM Local
    DOM.localAmplitud.innerHTML = `${homeM.amp.toFixed(1)} <small>m</small>`;
    DOM.localProfundidad.innerHTML = `${homeM.prof.toFixed(1)} <small>m</small>`;
    DOM.localArea.innerHTML = `${Math.round(homeM.area)} <small>m²</small>`;
    DOM.localCompacidad.innerHTML = `${homeM.comp.toFixed(1)} <small>m</small>`;

    DOM.fillLocalAmp.style.width = `${Math.min(100, (homeM.amp / 60) * 100)}%`;
    DOM.fillLocalProf.style.width = `${Math.min(100, (homeM.prof / 50) * 100)}%`;
    DOM.fillLocalArea.style.width = `${Math.min(100, (homeM.area / 1600) * 100)}%`;
    DOM.fillLocalComp.style.width = `${Math.min(100, (homeM.comp / 22) * 100)}%`;

    // Actualizar DOM Visitante
    DOM.awayAmplitud.innerHTML = `${awayM.amp.toFixed(1)} <small>m</small>`;
    DOM.awayProfundidad.innerHTML = `${awayM.prof.toFixed(1)} <small>m</small>`;
    DOM.awayArea.innerHTML = `${Math.round(awayM.area)} <small>m²</small>`;
    DOM.awayCompacidad.innerHTML = `${awayM.comp.toFixed(1)} <small>m</small>`;

    DOM.fillAwayAmp.style.width = `${Math.min(100, (awayM.amp / 60) * 100)}%`;
    DOM.fillAwayProf.style.width = `${Math.min(100, (awayM.prof / 50) * 100)}%`;
    DOM.fillAwayArea.style.width = `${Math.min(100, (awayM.area / 1600) * 100)}%`;
    DOM.fillAwayComp.style.width = `${Math.min(100, (awayM.comp / 22) * 100)}%`;
  }

  // --------------------------------------------------------------------------
  // 8. CICLO DE ANIMACIÓN Y REPRODUCCIÓN (60 FPS)
  // --------------------------------------------------------------------------
  let lastTimestamp = 0;

  function renderFrame(timestamp) {
    if (!lastTimestamp) lastTimestamp = timestamp;
    const deltaSec = (timestamp - lastTimestamp) / 1000.0;
    lastTimestamp = timestamp;

    if (MATCH_DATA.isPlaying) {
      MATCH_DATA.currentTime += deltaSec * MATCH_DATA.playbackSpeed;
      if (MATCH_DATA.currentTime >= MATCH_DATA.duration) {
        MATCH_DATA.currentTime = MATCH_DATA.duration;
        pause();
      }
      updateTimeDisplays();
    }

    // Obtener posiciones en el tiempo actual
    const currentData = getPlayersAtTime(MATCH_DATA.currentTime);

    // Dibujar Cancha 2D
    const pctx = DOM.pitchCanvas.getContext("2d");
    drawPitch(pctx, DOM.pitchCanvas.width, DOM.pitchCanvas.height, currentData, {
      showHull: DOM.chkShowHull.checked,
      showCentroid: DOM.chkShowCentroid.checked,
      showVectors: DOM.chkShowVectors.checked
    });

    // Dibujar Video Anotado
    const vctx = DOM.videoCanvas.getContext("2d");
    drawVideo(vctx, DOM.videoCanvas.width, DOM.videoCanvas.height, currentData);

    // Actualizar métricas de bloque
    updateBlockMetrics(currentData);

    requestAnimationFrame(renderFrame);
  }

  function updateTimeDisplays() {
    const formatted = formatTime(MATCH_DATA.currentTime);
    DOM.headerClock.textContent = formatted;
    DOM.currentTimeDisplay.textContent = formatted;

    const progressPct = (MATCH_DATA.currentTime / MATCH_DATA.duration) * 100;
    DOM.scrubberProgress.style.width = `${progressPct}%`;
    DOM.scrubberPlayhead.style.left = `${progressPct}%`;
  }

  function play() {
    MATCH_DATA.isPlaying = true;
    DOM.iconPlay.classList.add("hidden");
    DOM.iconPause.classList.remove("hidden");
  }

  function pause() {
    MATCH_DATA.isPlaying = false;
    DOM.iconPlay.classList.remove("hidden");
    DOM.iconPause.classList.add("hidden");
  }

  function togglePlay() {
    if (MATCH_DATA.isPlaying) pause();
    else play();
  }

  function seekTo(sec) {
    MATCH_DATA.currentTime = Math.max(0, Math.min(MATCH_DATA.duration, sec));
    updateTimeDisplays();
  }

  function jumpToEvent(sec, playerTrack = null) {
    seekTo(sec);
    switchView("tactica");

    if (playerTrack) {
      MATCH_DATA.highlightTrack = playerTrack;
      clearTimeout(MATCH_DATA.highlightTimer);
      MATCH_DATA.highlightTimer = setTimeout(() => {
        MATCH_DATA.highlightTrack = null;
      }, 4000);
      showToast(`Saltando a jugada ${formatTime(sec, false)} — Jugador #${playerTrack}`);
    } else {
      showToast(`Saltando al minuto ${formatTime(sec, false)}`);
    }
  }

  // --------------------------------------------------------------------------
  // 9. SISTEMA DE TAGUEO ONE-CLICK CON BUFFER DE -10s
  // --------------------------------------------------------------------------
  function createTag(type, customNote = null) {
    // Colchón de 10 segundos hacia atrás
    const bufferSec = 10.0;
    const tagTime = Math.max(0, MATCH_DATA.currentTime - bufferSec);

    const teamRadio = document.querySelector('input[name="tagTeam"]:checked');
    const selectedTeam = teamRadio ? teamRadio.value : "home";

    const newTag = {
      id: Date.now(),
      time: tagTime,
      type: type,
      team: selectedTeam,
      label: `${type} (Min ${formatTime(tagTime, false)})`,
      note: customNote || `Tagueado en vivo en ${formatTime(MATCH_DATA.currentTime, false)} (-10s buffer)`
    };

    taggedEvents.unshift(newTag);
    renderTaggedEvents();
    renderTimelineMarkers();
    showToast(`Jugada guardada: "${type}" en ${formatTime(tagTime, false)} (-10s)`);
  }

  function renderTaggedEvents() {
    DOM.taggedEventsList.innerHTML = "";
    DOM.tagCount.textContent = taggedEvents.length;

    taggedEvents.forEach((ev) => {
      const item = document.createElement("div");
      item.className = "feed-item";
      item.innerHTML = `
        <div class="feed-item-left">
          <span class="feed-item-time">${formatTime(ev.time, false)}</span>
          <span class="feed-item-badge">${ev.type}</span>
          <span class="feed-item-team">${ev.team === "home" ? "🔵 Local" : ev.team === "away" ? "🔴 Visitante" : "⚪ General"}</span>
        </div>
        <button class="feed-item-del" title="Eliminar jugada" data-id="${ev.id}">&times;</button>
      `;

      item.addEventListener("click", (e) => {
        if (e.target.classList.contains("feed-item-del")) {
          e.stopPropagation();
          deleteTag(ev.id);
          return;
        }
        jumpToEvent(ev.time);
      });

      DOM.taggedEventsList.appendChild(item);
    });
  }

  function deleteTag(id) {
    taggedEvents = taggedEvents.filter((ev) => ev.id !== id);
    renderTaggedEvents();
    renderTimelineMarkers();
  }

  function renderTimelineMarkers() {
    DOM.timelineMarkers.innerHTML = "";

    // Marcadores de tags
    taggedEvents.forEach((ev) => {
      const m = document.createElement("div");
      m.className = "timeline-event-marker tag";
      m.style.left = `${(ev.time / MATCH_DATA.duration) * 100}%`;
      m.title = `${ev.type} (${formatTime(ev.time, false)})`;
      m.addEventListener("click", (e) => {
        e.stopPropagation();
        jumpToEvent(ev.time);
      });
      DOM.timelineMarkers.appendChild(m);
    });

    // Marcadores de alertas de patrones tácticos
    const patternAlertTimes = [
      { t: 495.0, type: "alert-red", title: "Desconexión Defensiva #4 (08:15)" },
      { t: 872.0, type: "alert-red", title: "Línea sin achicar #2 (14:32)" },
      { t: 1160.0, type: "alert-yellow", title: "Bloque estirado (19:20)" },
      { t: 665.0, type: "alert-yellow", title: "Adelantamiento #8 (11:05)" }
    ];

    patternAlertTimes.forEach((pa) => {
      const m = document.createElement("div");
      m.className = `timeline-event-marker ${pa.type}`;
      m.style.left = `${(pa.t / MATCH_DATA.duration) * 100}%`;
      m.title = pa.title;
      m.addEventListener("click", (e) => {
        e.stopPropagation();
        jumpToEvent(pa.t);
      });
      DOM.timelineMarkers.appendChild(m);
    });
  }

  // --------------------------------------------------------------------------
  // 10. VISTA RENDIMIENTO INDIVIDUAL (TABLA & FICHA INSPECTORA)
  // --------------------------------------------------------------------------
  function renderPlayersTable() {
    DOM.playersTableBody.innerHTML = "";
    const roster = MATCH_DATA.selectedTeam === "home" ? HOME_ROSTER : AWAY_ROSTER;
    const query = DOM.playerSearchInput.value.toLowerCase().trim();

    const filtered = roster.filter((p) => {
      const matchesZone = MATCH_DATA.selectedZoneFilter === "all" || p.zone === MATCH_DATA.selectedZoneFilter;
      const matchesSearch = !query || p.name.toLowerCase().includes(query) || String(p.number) === query;
      return matchesZone && matchesSearch;
    });

    filtered.forEach((p) => {
      const tr = document.createElement("tr");
      if (p.id === MATCH_DATA.selectedPlayerId) tr.classList.add("selected");

      const distKm = (p.dist / 1000.0).toFixed(2);
      const ratingClass = p.rating === "green" ? "green" : p.rating === "yellow" ? "yellow" : "red";
      const ratingLabel = p.rating === "green" ? "🟢 Destacado" : p.rating === "yellow" ? "🟡 Regular" : "🔴 Bajo";

      tr.innerHTML = `
        <td><span class="table-jersey">#${p.number}</span></td>
        <td class="col-player">${p.name}</td>
        <td>${p.role}</td>
        <td>${p.min}'</td>
        <td>
          <div class="table-distance-cell">
            <span>${distKm} km</span>
            <div class="dist-bar-bg"><div class="dist-bar-fill" style="width: ${(p.dist / 12000) * 100}%;"></div></div>
          </div>
        </td>
        <td><strong>${p.maxSpd.toFixed(1)}</strong> <small>km/h</small></td>
        <td>${p.avgSpd.toFixed(1)} <small>km/h</small></td>
        <td>${p.sprints}</td>
        <td><span class="status-badge-inline ${ratingClass}">${ratingLabel}</span></td>
        <td>
          <button class="action-btn-secondary" style="padding: 3px 8px; font-size: 10.5px;" data-id="${p.id}">
            Inspeccionar
          </button>
        </td>
      `;

      tr.addEventListener("click", () => {
        selectPlayer(p.id);
      });

      DOM.playersTableBody.appendChild(tr);
    });
  }

  function selectPlayer(playerId) {
    MATCH_DATA.selectedPlayerId = playerId;
    const roster = [...HOME_ROSTER, ...AWAY_ROSTER];
    const player = roster.find((p) => p.id === playerId);
    if (!player) return;

    // Actualizar fila seleccionada en tabla
    document.querySelectorAll("#playersTableBody tr").forEach((row) => row.classList.remove("selected"));
    const selectedBtn = document.querySelector(`button[data-id="${playerId}"]`);
    if (selectedBtn) {
      selectedBtn.closest("tr").classList.add("selected");
    }

    // Actualizar encabezado del inspector
    DOM.inspectNum.textContent = `#${player.number}`;
    DOM.inspectName.textContent = player.name;
    DOM.inspectRole.textContent = `${player.role} · ${player.zone.toUpperCase()}`;

    const ratingClass = player.rating === "green" ? "var(--status-green)" : player.rating === "yellow" ? "var(--status-yellow)" : "var(--status-red)";
    const ratingText = player.rating === "green" ? "🟢 Destacado" : player.rating === "yellow" ? "🟡 Regular" : "🔴 Bajo Rendimiento";
    DOM.inspectRatingPill.style.color = ratingText.includes("🟢") ? "#000" : "#fff";
    DOM.inspectRatingPill.style.background = ratingClass;
    DOM.inspectRatingPill.textContent = ratingText;

    // Coordenada promedio
    DOM.centroidCoordinate.textContent = `X: ${player.posX.toFixed(1)}m · Y: ${player.posY.toFixed(1)}m (${player.posY > 45 ? "Banda Der." : player.posY < 23 ? "Banda Izq." : "Carril Central"})`;

    // Distribución física realista según su distancia
    const totalD = player.dist / 1000.0;
    const walkD = (totalD * 0.42).toFixed(1);
    const jogD = (totalD * 0.36).toFixed(1);
    const runD = (totalD * 0.16).toFixed(1);
    const sprintD = (totalD * 0.06).toFixed(1);

    DOM.valWalk.textContent = `${walkD} km (42%)`;
    DOM.valJog.textContent = `${jogD} km (36%)`;
    DOM.valRun.textContent = `${runD} km (16%)`;
    DOM.valSprint.textContent = `${sprintD} km (6%)`;

    // Notas del DT
    DOM.inspectDtNotes.textContent = player.note;

    // Dibujar mini cancha de calor / posición promedio
    drawInspectorPitch(player);
  }

  function drawInspectorPitch(player) {
    const canvas = DOM.inspectorPitchCanvas;
    const ctx = canvas.getContext("2d");
    const W = canvas.width;
    const H = canvas.height;

    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = "#14331e";
    ctx.fillRect(0, 0, W, H);

    const sx = (mx) => (mx / 105.0) * W;
    const sy = (my) => (my / 68.0) * H;

    // Líneas tenues
    ctx.strokeStyle = "rgba(255, 255, 255, 0.4)";
    ctx.lineWidth = 1;
    ctx.strokeRect(sx(0), sy(0), sx(105), sy(68));
    ctx.beginPath();
    ctx.moveTo(sx(52.5), sy(0));
    ctx.lineTo(sx(52.5), sy(68));
    ctx.stroke();
    ctx.strokeRect(sx(0), sy(14), sx(16.5), sy(40));
    ctx.strokeRect(sx(105 - 16.5), sy(14), sx(16.5), sy(40));

    // Elipse de dispersión / Huella de calor del jugador
    const px = sx(player.posX);
    const py = sy(player.posY);
    const grad = ctx.createRadialGradient(px, py, 4, px, py, 45);
    grad.addColorStop(0, "rgba(195, 255, 0, 0.55)");
    grad.addColorStop(0.5, "rgba(56, 189, 248, 0.25)");
    grad.addColorStop(1, "rgba(0, 0, 0, 0)");

    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(px, py, 45, 30, 0, 0, Math.PI * 2);
    ctx.fill();

    // Punto del centroide promedio
    ctx.fillStyle = "#ffffff";
    ctx.beginPath();
    ctx.arc(px, py, 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = "#c3ff00";
    ctx.lineWidth = 2;
    ctx.stroke();

    // Número
    ctx.fillStyle = "#000000";
    ctx.font = "bold 8px monospace";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(player.number, px, py);
  }

  // --------------------------------------------------------------------------
  // 11. VISTA SEMÁFORO POST-PARTIDO
  // --------------------------------------------------------------------------
  function renderSemaforo() {
    DOM.semaforoRosterGrid.innerHTML = "";
    let countG = 0, countY = 0, countR = 0;

    HOME_ROSTER.forEach((p) => {
      if (p.rating === "green") countG++;
      else if (p.rating === "yellow") countY++;
      else if (p.rating === "red") countR++;

      const card = document.createElement("div");
      card.className = "semaforo-card";
      card.innerHTML = `
        <div class="sc-header">
          <div class="sc-player-info">
            <span class="sc-jersey">#${p.number}</span>
            <div>
              <h4 class="sc-name">${p.name}</h4>
              <span class="sc-role">${p.role}</span>
            </div>
          </div>
          <span class="sc-stat-pill">${(p.dist / 1000).toFixed(1)} km · Pico ${p.maxSpd.toFixed(1)} km/h</span>
        </div>

        <div class="sc-selector-row">
          <button class="state-btn btn-green ${p.rating === "green" ? "active" : ""}" data-val="green">
            🟢 Destacado
          </button>
          <button class="state-btn btn-yellow ${p.rating === "yellow" ? "active" : ""}" data-val="yellow">
            🟡 Regular
          </button>
          <button class="state-btn btn-red ${p.rating === "red" ? "active" : ""}" data-val="red">
            🔴 Bajo
          </button>
        </div>

        <input type="text" class="sc-note-input" value="${p.note}" placeholder="Nota táctica para la semana de trabajo...">
      `;

      // Eventos de botones de estado
      const stateBtns = card.querySelectorAll(".state-btn");
      stateBtns.forEach((btn) => {
        btn.addEventListener("click", () => {
          stateBtns.forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          p.rating = btn.dataset.val;
          updateSemaforoScoreboard();
          renderPlayersTable(); // Sincroniza con la tabla
          showToast(`Calificación actualizada para #${p.number} ${p.name}`);
        });
      });

      // Input de nota
      const noteInput = card.querySelector(".sc-note-input");
      noteInput.addEventListener("change", () => {
        p.note = noteInput.value;
      });

      DOM.semaforoRosterGrid.appendChild(card);
    });

    updateSemaforoScoreboard();
  }

  function updateSemaforoScoreboard() {
    let countG = 0, countY = 0, countR = 0;
    HOME_ROSTER.forEach((p) => {
      if (p.rating === "green") countG++;
      else if (p.rating === "yellow") countY++;
      else if (p.rating === "red") countR++;
    });

    const total = HOME_ROSTER.length;
    DOM.countVerde.textContent = countG;
    DOM.countAmarillo.textContent = countY;
    DOM.countRojo.textContent = countR;

    DOM.pctVerde.textContent = `${Math.round((countG / total) * 100)}% del plantel`;
    DOM.pctAmarillo.textContent = `${Math.round((countY / total) * 100)}% del plantel`;
    DOM.pctRojo.textContent = `${Math.round((countR / total) * 100)}% del plantel`;
  }

  function generateWhatsAppReport() {
    const now = new Date();
    const dateStr = now.toLocaleDateString("es-AR", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

    let msg = `*ANALIZADOR TÁCTICO — INFORME POST-PARTIDO*\n`;
    msg += `⚽ Sportivo Belgrano (2) vs. Alumni (1) — Fecha 12\n`;
    msg += `📅 ${dateStr}\n\n`;

    msg += `*1. BALANCE DEL SEMÁFORO*\n`;
    msg += `🟢 Destacados: ${DOM.countVerde.textContent} jugadores\n`;
    msg += `🟡 Regulares: ${DOM.countAmarillo.textContent} jugadores\n`;
    msg += `🔴 Bajo rendimiento: ${DOM.countRojo.textContent} jugador\n\n`;

    msg += `*2. CALIFICACIÓN JUGADOR POR JUGADOR*\n`;
    HOME_ROSTER.forEach((p) => {
      const emoji = p.rating === "green" ? "🟢" : p.rating === "yellow" ? "🟡" : "🔴";
      msg += `${emoji} *#${p.number} ${p.name}* (${p.role})\n`;
      msg += `   Distancia: ${(p.dist / 1000).toFixed(1)} km | Vel. Máx: ${p.maxSpd.toFixed(1)} km/h\n`;
      if (p.note) msg += `   Nota: _${p.note}_\n`;
    });

    msg += `\n*3. ALERTAS TÁCTICAS PRIORITARIAS PARA EL MARTES*\n`;
    msg += `⚠️ *Línea Defensiva:* Ajustar repliegue de #4 Lucas Rossi (desconexión de 13.8m detectada).\n`;
    msg += `⚠️ *Avance en Bloque:* Exigir que los centrales achiquen cuando el mediocampo presiona.\n`;
    msg += `\n_Generado automáticamente por Analizador Táctico (UTN FRSF)_`;

    return msg;
  }

  // --------------------------------------------------------------------------
  // 12. NAVEGACIÓN Y EVENT LISTENERS
  // --------------------------------------------------------------------------
  function switchView(viewName) {
    MATCH_DATA.activeView = viewName;

    DOM.navButtons.forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.view === viewName);
    });

    DOM.viewContainers.forEach((cont) => {
      cont.classList.toggle("active", cont.id === `view${viewName.charAt(0).toUpperCase() + viewName.slice(1)}`);
    });

    // Si entra a la vista de jugadores, dibujar la cancha del inspector
    if (viewName === "jugadores") {
      selectPlayer(MATCH_DATA.selectedPlayerId);
    }
  }

  function setupEventListeners() {
    // 1. Navegación superior
    DOM.navButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        switchView(btn.dataset.view);
      });
    });

    // 2. Modos de visor de Mesa Táctica (Split / Cancha / Video)
    DOM.modeButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        DOM.modeButtons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");

        DOM.screensWrapper.className = `screens-grid ${btn.dataset.mode === "split" ? "split" : btn.dataset.mode === "pitch" ? "pitch-only" : "video-only"}`;
      });
    });

    // 3. Controles de transporte
    DOM.btnPlayPause.addEventListener("click", togglePlay);
    DOM.btnStepBack.addEventListener("click", () => seekTo(MATCH_DATA.currentTime - 0.5));
    DOM.btnStepForward.addEventListener("click", () => seekTo(MATCH_DATA.currentTime + 0.5));

    DOM.speedButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        DOM.speedButtons.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        MATCH_DATA.playbackSpeed = parseFloat(btn.dataset.speed);
      });
    });

    // 4. Scrubber manual (arrastre o clic)
    const handleScrub = (e) => {
      const rect = DOM.scrubberTrack.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const ratio = Math.max(0, Math.min(1, clickX / rect.width));
      seekTo(ratio * MATCH_DATA.duration);
    };

    let isScrubbing = false;
    DOM.scrubberTrack.addEventListener("mousedown", (e) => {
      isScrubbing = true;
      handleScrub(e);
    });
    window.addEventListener("mousemove", (e) => {
      if (isScrubbing) handleScrub(e);
    });
    window.addEventListener("mouseup", () => {
      isScrubbing = false;
    });

    // 5. Botones de Tagueo
    DOM.tagButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        createTag(btn.dataset.tag);
      });
    });

    // 6. Atajos de Teclado
    window.addEventListener("keydown", (e) => {
      // Si el foco está en un input de texto, no disparar atajos de reproducción
      if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

      if (e.code === "Space") {
        e.preventDefault();
        togglePlay();
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        seekTo(MATCH_DATA.currentTime - (e.shiftKey ? 5.0 : 1.0));
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        seekTo(MATCH_DATA.currentTime + (e.shiftKey ? 5.0 : 1.0));
      } else if (e.key.toLowerCase() === "p") {
        createTag("Presión");
      } else if (e.key.toLowerCase() === "s") {
        createTag("Salida");
      } else if (e.key.toLowerCase() === "t") {
        createTag("Transición");
      } else if (e.key.toLowerCase() === "b") {
        createTag("Pelota Parada");
      } else if (e.key.toLowerCase() === "r") {
        createTag("Recuperación");
      } else if (e.key.toLowerCase() === "x") {
        createTag("Pérdida");
      }
    });

    // 7. Filtros de vista Jugadores
    DOM.teamFilterBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        DOM.teamFilterBtns.forEach((b) => b.classList.remove("active"));
        btn.classList.add("active");
        MATCH_DATA.selectedTeam = btn.dataset.team;
        renderPlayersTable();
        // Seleccionar primer jugador de este equipo
        const first = MATCH_DATA.selectedTeam === "home" ? HOME_ROSTER[0] : AWAY_ROSTER[0];
        selectPlayer(first.id);
      });
    });

    DOM.zonePills.forEach((pill) => {
      pill.addEventListener("click", () => {
        DOM.zonePills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        MATCH_DATA.selectedZoneFilter = pill.dataset.zone;
        renderPlayersTable();
      });
    });

    DOM.playerSearchInput.addEventListener("input", renderPlayersTable);

    // Botón de salto de jugador a video
    DOM.btnJumpPlayerVideo.addEventListener("click", () => {
      const roster = [...HOME_ROSTER, ...AWAY_ROSTER];
      const p = roster.find((x) => x.id === MATCH_DATA.selectedPlayerId);
      if (p) {
        jumpToEvent(MATCH_DATA.currentTime, p.number);
      }
    });

    // 8. Vista Patrones: Filtro de severidad y botones de inspección
    DOM.sevPills.forEach((pill) => {
      pill.addEventListener("click", () => {
        DOM.sevPills.forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        const sev = pill.dataset.sev;

        document.querySelectorAll(".pattern-card").forEach((card) => {
          if (sev === "all" || card.dataset.sev === sev) {
            card.style.display = "flex";
          } else {
            card.style.display = "none";
          }
        });
      });
    });

    // Botones "Ver jugada" dentro de las tarjetas de patrones
    document.querySelectorAll(".btn-inspect-clip, .ts-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const seekSec = parseFloat(btn.dataset.seek);
        const card = btn.closest(".pattern-card");
        let trackNum = null;
        if (card) {
          const leadNum = card.querySelector(".lead-num");
          if (leadNum) {
            trackNum = parseInt(leadNum.textContent.replace("#", ""));
          }
        }
        jumpToEvent(seekSec, trackNum);
      });
    });

    // 9. Modal de Reporte para WhatsApp
    const openReportModal = () => {
      const text = generateWhatsAppReport();
      DOM.reportTextarea.value = text;
      DOM.copyStatusMsg.textContent = "";
      DOM.reportModal.classList.remove("hidden");
    };

    DOM.btnQuickReport.addEventListener("click", openReportModal);
    DOM.btnExportWhatsApp.addEventListener("click", openReportModal);

    DOM.btnCloseModal.addEventListener("click", () => {
      DOM.reportModal.classList.add("hidden");
    });

    DOM.btnCopyReport.addEventListener("click", () => {
      navigator.clipboard.writeText(DOM.reportTextarea.value).then(() => {
        DOM.copyStatusMsg.textContent = "✅ ¡Copiado al portapapeles!";
        showToast("Informe copiado listo para enviar por WhatsApp");
      });
    });

    // Restablecer calificaciones
    DOM.btnResetSemaforo.addEventListener("click", () => {
      HOME_ROSTER.forEach((p, idx) => {
        p.rating = idx === 1 ? "red" : idx === 2 ? "yellow" : "green";
      });
      renderSemaforo();
      renderPlayersTable();
      showToast("Calificaciones restablecidas a valores base");
    });
  }

  // --------------------------------------------------------------------------
  // 13. INICIALIZACIÓN DE LA APLICACIÓN
  // --------------------------------------------------------------------------
  function init() {
    updateTimeDisplays();
    renderTaggedEvents();
    renderTimelineMarkers();
    renderPlayersTable();
    selectPlayer(MATCH_DATA.selectedPlayerId);
    renderSemaforo();
    setupEventListeners();

    // Arrancar loop de renderizado a 60 fps
    requestAnimationFrame(renderFrame);
  }

  // Ejecutar al cargar la página
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
