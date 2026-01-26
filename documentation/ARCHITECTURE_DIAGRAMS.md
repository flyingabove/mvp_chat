# MVPChat Architecture Diagrams

Visual representation of the StoriesChat codebase structure, data flows, and dependencies.

---

## 1. System Architecture Layers

```mermaid
graph TB
    subgraph Frontend["Frontend Layer"]
        HTML["index.html<br/>Terminal UI"]
    end
    
    subgraph API["API Layer"]
        Chat["chat.py<br/>Main Endpoint"]
        Stories["stories.py<br/>List Stories"]
        Story["story.py<br/>Story Meta"]
        Health["health.py<br/>Health Check"]
        Echo["echo.py<br/>Echo Debug"]
        Game["game_logic.py<br/>Unused"]
    end
    
    subgraph Engine["Engine Layer"]
        State["state.py<br/>Game State"]
        StoryLoader["story_loader.py<br/>Story Loading"]
        Gameplay["gameplay.py<br/>Time & Confession"]
        PromptBuilder["prompt_builder.py<br/>LLM Prompt"]
        LocationExtractor["location_extractor.py<br/>LLM Movement"]
        TimeUtils["time_utils.py<br/>Timestamps"]
    end
    
    subgraph World["World Engine"]
        WorldLoader["world_loader.py<br/>Load World"]
        WorldJSON["world_json.py<br/>Parse World"]
        Graph["graph.py<br/>Graph Structure"]
        Location["location.py<br/>Locations"]
        Edge["edge.py<br/>Edges"]
        Clock["clock.py<br/>World Time"]
        TravelRules["travel_rules.py<br/>Path Finding"]
        TravelResolver["travel_resolver.py<br/>Travel Exec"]
        Exposure["exposure.py<br/>Character Exposure"]
    end
    
    subgraph Knowledge["Knowledge Layer"]
        Retrieve["retrieve.py<br/>Hybrid Search"]
        IndexService["index_service.py<br/>Index Cache"]
        LoadIndexes["load_indexes.py<br/>Load FAISS/BM25"]
        FAISSRuntime["faiss_runtime.py<br/>FAISS Search"]
        BM25Runtime["bm25_runtime.py<br/>BM25 Search"]
        EnsureCache["ensure_cache.py<br/>Cache Init"]
    end
    
    subgraph Build["Build Pipeline"]
        BuildIndex["build_index.py<br/>Build Main"]
        Embedder["embedder.py<br/>Embeddings"]
        FAISSUtils["faiss_utils.py<br/>FAISS Build"]
        BM25Utils["bm25_utils.py<br/>BM25 Build"]
        Fingerprint["fingerprint.py<br/>Cache Check"]
        Hybrid["hybrid.py<br/>Fusion"]
        AuthorCheck["authoring_checklist.py<br/>Validate"]
    end
    
    subgraph Infra["Infrastructure"]
        Settings["settings.py<br/>Config"]
        Middleware["request_id.py<br/>Tracing"]
        Main["main.py<br/>FastAPI App"]
        Contract["index_bundle.py<br/>Types"]
    end
    
    HTML -->|POST /chat| Chat
    HTML -->|GET /stories| Stories
    HTML -->|GET /story/:id| Story
    
    Chat --> State
    Chat --> StoryLoader
    Chat --> LocationExtractor
    Chat --> PromptBuilder
    Chat --> Retrieve
    Chat --> Gameplay
    Chat --> WorldLoader
    Chat --> TimeUtils
    
    LocationExtractor --> WorldLoader
    PromptBuilder --> Gameplay
    
    WorldLoader --> WorldJSON
    WorldLoader --> Graph
    WorldLoader --> Clock
    WorldLoader --> TravelResolver
    WorldLoader --> Exposure
    
    Graph --> Location
    Graph --> Edge
    TravelResolver --> TravelRules
    TravelResolver --> Clock
    
    Retrieve --> IndexService
    IndexService --> LoadIndexes
    LoadIndexes --> FAISSRuntime
    LoadIndexes --> BM25Runtime
    
    BuildIndex --> Embedder
    BuildIndex --> FAISSUtils
    BuildIndex --> BM25Utils
    BuildIndex --> Fingerprint
    BuildIndex --> Hybrid
    BuildIndex --> AuthorCheck
    
    Main --> EnsureCache
    Main --> Chat
    
    Chat -.->|uses| Settings
    Chat -.->|uses| Middleware
    
    Build -.->|builds| Knowledge
```

---

## 2. Chat Turn Request Flow

```mermaid
sequenceDiagram
    participant Frontend as Frontend<br/>Terminal UI
    participant API as API Layer<br/>chat_handler()
    participant Engine as Engine Layer<br/>State/Gameplay
    participant World as World Engine<br/>Navigation
    participant Knowledge as Knowledge<br/>Retrieval
    participant LLM as OpenAI API<br/>GPT-4o-mini
    
    Frontend->>API: POST /chat {session_id, message}
    
    API->>Engine: get_session() / init_state()
    API->>Engine: load_story(story_id)
    
    API->>Engine: LocationExtractor._should_attempt()
    Engine->>LLM: Classify: Is this movement?
    LLM-->>Engine: {is_movement_intent: bool}
    
    alt Movement Detected
        API->>Engine: LocationExtractor.extract()
        Engine->>LLM: Extract: What's destination?
        LLM-->>Engine: {destination_id: str}
        Engine->>World: Validate in world_graph.locations
    end
    
    API->>Knowledge: retrieve_knowledge(message)
    Knowledge->>Knowledge: BM25 search
    Knowledge->>Knowledge: FAISS search
    Knowledge->>Knowledge: hybrid_retrieve() fusion
    Knowledge-->>API: chunks []
    
    API->>Engine: build_messages(state, log, message, chunks)
    
    API->>LLM: POST chat/completions {messages, temp=0.8}
    LLM-->>API: response text + [[STATE: {...}]]
    
    API->>Engine: extract_state_tag(reply)
    Engine-->>API: (clean_reply, state_dict)
    
    API->>Engine: apply_state_tag(state, state_dict)
    API->>Engine: advance_time(state, message)
    
    alt Location Changed
        Engine->>World: travel_resolver.resolve(from, to)
        World->>World: compute route, exposure
    end
    
    API->>Engine: confession_detected(reply, state)
    
    API-->>Frontend: {reply, over, debug_info}
    Frontend->>Frontend: typewriter animation
    Frontend->>Frontend: render response
```

---

## 3. Knowledge Retrieval Pipeline

```mermaid
graph LR
    Query["User Query<br/>String"]
    
    subgraph Indexing["Index Service"]
        Cache["Character<br/>Index Bundle<br/>Cache"]
        Active["set_active_<br/>character()"]
    end
    
    subgraph Search["Search Layer"]
        BM25["BM25<br/>Keyword<br/>Search"]
        FAISS["FAISS<br/>Semantic<br/>Search"]
    end
    
    subgraph Fusion["Result Fusion"]
        Hybrid["hybrid_retrieve()<br/>Rank & Fuse"]
    end
    
    Results["Retrieved<br/>Chunks []"]
    PromptBuilder["build_messages()<br/>Inject Context"]
    LLM["OpenAI API<br/>Chat Completion"]
    
    Query --> Indexing
    Active --> Cache
    Cache -->|chunks| BM25
    Cache -->|embeddings| FAISS
    
    BM25 -->|lexical results| Fusion
    FAISS -->|semantic results| Fusion
    
    Fusion --> Hybrid
    Hybrid --> Results
    
    Results --> PromptBuilder
    PromptBuilder --> LLM
```

---

## 4. World System Architecture

```mermaid
graph TB
    subgraph Load["Loading Phase"]
        JSON["World JSON<br/>File"]
        JSONLoader["WorldDefinition<br/>Loader"]
        Parse["Parse<br/>Locations & Edges"]
    end
    
    subgraph Runtime["Runtime Phase"]
        Graph["WorldGraph<br/>locations {}"]
        Locs["Location<br/>Objects"]
        Edges["PathEdge<br/>Objects"]
        
        Clock["WorldClock<br/>minute counter"]
        
        Rules["TravelRules<br/>Path finding"]
        Resolver["TravelResolver<br/>Travel execution"]
        Exposure["ExposureResolver<br/>Character sightings"]
    end
    
    subgraph Result["LoadResult"]
        WLR["WorldLoadResult<br/>graph + clock<br/>+ resolver"]
    end
    
    subgraph GameState["Game State"]
        State["MurderGameState<br/>location_id, minute<br/>world_runtime"]
    end
    
    subgraph Actions["Player Actions"]
        ExtractLoc["LocationExtractor<br/>Extract destination"]
        CanonicMove["Canonicalize<br/>to 'go to X'"]
        Travel["advance_time()<br/>travel_resolver.resolve()"]
    end
    
    JSON --> JSONLoader
    JSONLoader --> Parse
    Parse -->|locations| Locs
    Parse -->|edges| Edges
    
    Locs --> Graph
    Edges --> Graph
    
    Graph --> WLR
    Clock --> WLR
    Rules --> Resolver
    Exposure --> Resolver
    Resolver --> WLR
    
    WLR --> State
    
    ExtractLoc --> CanonicMove
    CanonicMove --> Travel
    Travel -->|uses| Resolver
    Travel -->|updates| State
```

---

## 5. State Management & Updates

```mermaid
graph TB
    subgraph Initial["Game Initialization"]
        Init["init_state()"]
        StoryConfig["Load story_cfg"]
        PlayerInfo["Set player_name<br/>gender"]
        CharInit["Initialize<br/>characters{}"]
    end
    
    subgraph Session["During Session"]
        State["MurderGameState"]
        
        subgraph Dynamics["Character Dynamics"]
            Emotion["emotion: str"]
            Relation["relationship: int"]
        end
        
        subgraph Location["World Position"]
            LocID["location_id: str"]
            LocDisp["location: str"]
            Minute["minute: int"]
        end
        
        subgraph Flags["Status Flags"]
            Over["over: bool"]
            Turns["turns: int"]
        end
    end
    
    subgraph Updates["State Updates"]
        StateTags["[[STATE: {...}]]<br/>from LLM"]
        Extract["extract_state_tag()"]
        Apply["apply_state_tag()"]
        
        LocationExt["LocationExtractor<br/>extract()"]
        Travel["advance_time()<br/>+ travel"]
    end
    
    subgraph Checks["End Conditions"]
        Confession["confession_detected()"]
        GameEnd["Set over=true"]
    end
    
    Init --> State
    StoryConfig --> State
    PlayerInfo --> State
    CharInit --> State
    
    State --> Dynamics
    State --> Location
    State --> Flags
    
    StateTags --> Extract
    Extract --> Apply
    Apply --> Dynamics
    
    LocationExt --> State
    Travel --> Location
    
    Confession --> GameEnd
    GameEnd --> Flags
```

---

## 6. LLM Integration Points

```mermaid
graph TB
    subgraph Calls["LLM API Calls"]
        C1["1. LocationExtractor<br/>._should_attempt()<br/><br/>Classify: Is movement?"]
        C2["2. LocationExtractor<br/>.extract()<br/><br/>Extract: destination_id"]
        C3["3. build_messages()<br/>→ OpenAI Chat<br/><br/>Generate dialogue"]
    end
    
    subgraph Inputs["Inputs"]
        I1["Current location<br/>Recent history"]
        I2["Known world<br/>locations list"]
        I3["Character context<br/>Retrieved knowledge<br/>Emotion/relationship<br/>Manifestation rules"]
    end
    
    subgraph Parsing["Output Parsing"]
        P1["Boolean: true/false"]
        P2["JSON:<br/>destination_id<br/>confidence"]
        P3["Text + STATE tag<br/>[[STATE: emotion<br/>rel_delta]]"]
    end
    
    subgraph Actions["Actions"]
        A1["Skip/attempt<br/>extraction"]
        A2["Update<br/>location_id<br/>canonicalize move"]
        A3["Update state<br/>emotion/relationship<br/>Check confession"]
    end
    
    C1 --> I1
    C2 --> I2
    C3 --> I3
    
    C1 --> P1 --> A1
    C2 --> P2 --> A2
    C3 --> P3 --> A3
```

---

## 7. File Dependency Graph

```mermaid
graph TB
    ChatPy["chat.py<br/>CORE ORCHESTRATOR"]
    
    ChatPy --> StatePy["state.py<br/>MurderGameState"]
    ChatPy --> StoryLoaderPy["story_loader.py<br/>load_story()"]
    ChatPy --> LocationExtPy["location_extractor.py<br/>LLM extraction"]
    ChatPy --> PromptBuilderPy["prompt_builder.py<br/>build_messages()"]
    ChatPy --> GameplayPy["gameplay.py<br/>advance_time()"]
    ChatPy --> RetrievePy["retrieve.py<br/>retrieve_knowledge()"]
    ChatPy --> WorldLoaderPy["world_loader.py<br/>Load world"]
    
    LocationExtPy --> WorldLoaderPy
    GameplayPy --> WorldLoaderPy
    
    WorldLoaderPy --> WorldJSONPy["world_json.py"]
    WorldLoaderPy --> GraphPy["graph.py"]
    WorldLoaderPy --> ClockPy["clock.py"]
    WorldLoaderPy --> TravelResolverPy["travel_resolver.py"]
    
    GraphPy --> LocationPy["location.py"]
    GraphPy --> EdgePy["edge.py"]
    
    TravelResolverPy --> TravelRulesPy["travel_rules.py"]
    TravelResolverPy --> ExposurePy["exposure.py"]
    
    RetrievePy --> IndexServicePy["index_service.py"]
    IndexServicePy --> LoadIndexesPy["load_indexes.py"]
    
    LoadIndexesPy --> FAISSRuntimePy["faiss_runtime.py"]
    LoadIndexesPy --> BM25RuntimePy["bm25_runtime.py"]
    
    MainPy["main.py"] --> EnsureIndexesPy["ensure_indexes.py"]
    EnsureIndexesPy --> BuildIndexPy["build_index.py"]
    
    BuildIndexPy --> EmbedderPy["embedder.py"]
    BuildIndexPy --> FAISSUtilsPy["faiss_utils.py"]
    BuildIndexPy --> BM25UtilsPy["bm25_utils.py"]
    BuildIndexPy --> FingerprintPy["fingerprint.py"]
    BuildIndexPy --> HybridPy["hybrid.py"]
    
    MainPy --> SettingsPy["settings.py"]
    MainPy --> MiddlewarePy["request_id.py"]
    MainPy --> HealthPy["health.py"]
    MainPy --> StoriesPy["stories.py"]
    
    style ChatPy fill:#ff6b6b
    style StatePy fill:#4ecdc4
    style WorldLoaderPy fill:#45b7d1
    style RetrievePy fill:#96ceb4
    style BuildIndexPy fill:#ffeaa7
```

---

## 8. Class Hierarchy & Relationships

```mermaid
graph TD
    subgraph State["State Classes"]
        UState["UserState<br/>formal_name, gender<br/>display_name"]
        CState["CharacterState<br/>key, name, role<br/>emotion, relationship"]
        MGState["MurderGameState<br/>story_cfg, characters{}<br/>location_id, minute<br/>world_runtime, emotion<br/>relationship"]
    end
    
    subgraph World["World Classes"]
        Loc["Location<br/>id, name, description<br/>tags, allows_phone"]
        Edge["PathEdge<br/>from_id, to_id<br/>minutes, blocked"]
        Graph["WorldGraph<br/>locations{}, add_*<br/>get_location(), edges"]
        Clock["WorldClock<br/>minute, advance()<br/>advance_minutes()"]
        TRules["TravelRules<br/>resolve_route()<br/>choose_edge()"]
        TRes["TravelResolver<br/>execute()<br/>resolve()"]
        Exp["ExposureResolver<br/>roll()"]
    end
    
    subgraph Location["Location Extraction"]
        Intent["LocationIntent<br/>NONE, MOVE"]
        Extract["LocationExtraction<br/>intent, destination_id<br/>confidence"]
        Extractor["LocationExtractor<br/>_should_attempt()<br/>extract()"]
    end
    
    subgraph Knowledge["Knowledge Classes"]
        Bundle["CharacterIndexBundle<br/>chunks, faiss_index<br/>bm25_index, embeddings"]
        Service["IndexService<br/>get_indexes()<br/>set_active_character()"]
    end
    
    MGState --> UState
    MGState --> CState
    MGState -.contains.-> Clock
    MGState -.contains.-> TRes
    
    Graph --> Loc
    Graph --> Edge
    TRules --> Graph
    TRes --> TRules
    TRes --> Clock
    TRes --> Exp
    
    Extractor --> Intent
    Extractor --> Extract
    
    Service --> Bundle
```

---

## 9. Data Flow: Complete Chat Turn

```mermaid
graph LR
    Input["User Input<br/>Message String"]
    
    Input -->|Parse| Parse["Command?<br/>Debug Toggle?<br/>Normal Msg?"]
    
    Parse -->|New Game| NewGame["__cmd_newgame__<br/>Load Story<br/>Init State<br/>Load World"]
    Parse -->|Normal| Process["Extract Name?<br/>Location?"]
    
    NewGame --> Loaded["State Ready<br/>With Story Config"]
    
    Process -->|Name Detect| NameConfirm["Ask Confirm<br/>Return prompt"]
    Process -->|No Name| ContinueTurn["Continue Turn"]
    
    NameConfirm -->|Yes| UpdateName["Update state<br/>player_name"]
    NameConfirm -->|No| AskAgain["Retry"]
    
    UpdateName --> ContinueTurn
    
    ContinueTurn -->|Extract Location| LocExt["LocationExtractor<br/>._should_attempt()<br/>.extract()"]
    LocExt -->|Move Detected| CanonMove["Canonicalize:<br/>go to {dest_id}"]
    LocExt -->|No Move| OrigMsg["Keep original msg"]
    
    CanonMove --> Retrieve["retrieve_knowledge()<br/>BM25 + FAISS<br/>Hybrid fusion"]
    OrigMsg --> Retrieve
    
    Retrieve --> Knowledge["Chunks []"]
    Knowledge --> BuildMsg["build_messages()<br/>System prompt<br/>Memory block<br/>History"]
    
    BuildMsg --> Messages["OpenAI message list"]
    Messages --> LLM["POST chat/completions"]
    
    LLM --> Reply["LLM response<br/>text + STATE tag"]
    Reply -->|Parse| ParseTag["extract_state_tag()"]
    
    ParseTag --> Clean["Clean reply<br/>State dict"]
    
    Clean -->|Apply| ApplyState["apply_state_tag()<br/>Update emotion<br/>Update relationship"]
    ApplyState --> StateUpdated["State modified"]
    
    Clean -->|Time| AdvanceTime["advance_time()<br/>Word count → minutes<br/>Location changed?"]
    AdvanceTime -->|Yes| Travel["travel_resolver.resolve()<br/>Add travel time<br/>Roll exposure"]
    AdvanceTime -->|No| NoTravel["Just increment minute"]
    
    Travel --> TimeAdvanced["Minute updated"]
    NoTravel --> TimeAdvanced
    
    StateUpdated --> Check["confession_detected()?"]
    Check -->|Yes| Won["over = true<br/>Show ending"]
    Check -->|No| Reply2["over = false<br/>Continue game"]
    
    Won --> Output["Return<br/>reply + over<br/>+ debug_info"]
    Reply2 --> Output
    
    Output --> Frontend["Send to Frontend<br/>Typewriter effect"]
```

---

## 10. Build & Deployment Pipeline

```mermaid
graph TB
    subgraph Source["Source Code"]
        CharDir["backend/app/<br/>knowledge/characters/<br/>CHAR_ID/"]
        Chunks["chunks.md<br/>Chunks of text"]
    end
    
    subgraph BuildPhase["Build Phase<br/>Docker Build Time"]
        Validate["validate_chunks()"]
        Fingerprint["load_previous_build()"]
        Skip["should_skip()?"]
        
        Embed["Embedder<br/>.embed_text()"]
        FAISSBuild["build_faiss_index()"]
        BM25Build["build_bm25_index()"]
        
        SaveJSON["_atomic_save_json()"]
        SaveNPY["_atomic_save_npy()"]
        SaveFP["save_fingerprint()"]
    end
    
    subgraph Cache["Cache Directory<br/>/data/knowledge_cache/CHAR_ID/"]
        ChunkFile["chunks.jsonl"]
        EmbFile["embeddings.npy"]
        FAISSFile["faiss.index"]
        BM25File["bm25.pkl"]
        FPFile["fingerprint.json"]
    end
    
    subgraph Runtime["Runtime Phase<br/>App Startup"]
        EnsureIdxs["ensure_indexes()"]
        Load["load_character_indexes()"]
        Warm["warm_indexes()"]
    end
    
    subgraph App["Running App"]
        IndexSvc["IndexService<br/>Cache + Context"]
        Retrieve["retrieve_knowledge()"]
    end
    
    Source --> Validate
    Validate --> Fingerprint
    Fingerprint --> Skip
    
    Skip -->|No Skip| Embed
    Skip -->|Skip| Done["Use cached"]
    
    Embed --> FAISSBuild
    Embed --> BM25Build
    
    FAISSBuild --> SaveJSON
    BM25Build --> SaveJSON
    SaveJSON --> SaveNPY
    SaveNPY --> SaveFP
    
    SaveJSON --> Cache
    SaveNPY --> Cache
    SaveFP --> Cache
    Done --> Cache
    
    Cache --> EnsureIdxs
    EnsureIdxs --> Load
    Load --> Warm
    
    Warm --> App
    App --> IndexSvc
    IndexSvc --> Retrieve
```

---

## 11. Unused Code Diagram

```mermaid
graph LR
    Unused["Unused Code<br/>(Dead Ends)"]
    
    Unused --> GameLogic["game_logic.py<br/>Placeholder endpoint<br/>No callers"]
    
    Unused --> SearchBM25["bm25_runtime.py<br/>search_bm25()<br/>Not called<br/>Retrieval inline"]
```

---

## 12. Key Metrics

```
┌─────────────────────────────────────────────────┐
│  Code Statistics                                │
├─────────────────────────────────────────────────┤
│  Backend Python Files              39           │
│  Backend Classes                   ~40          │
│  Backend Methods/Functions         ~150         │
│  Frontend JS Functions             ~30          │
│                                                 │
│  LLM API Calls Per Turn             3           │
│  │ 1. Classification                            │
│  │ 2. Destination Extraction                    │
│  │ 3. Dialogue Generation                       │
│                                                 │
│  State Transitions Per Turn        ~5           │
│  │ Location, Minute, Emotion, Etc.              │
│                                                 │
│  Knowledge Indexes                 2           │
│  │ FAISS (semantic)                             │
│  │ BM25 (lexical)                               │
│                                                 │
│  Unused Functions                  2           │
│  All Other Functions              ~148 (98%)    │
│                                                 │
│  Layers                            5           │
│  │ Frontend → API → Engine →                    │
│  │ World → Knowledge                            │
└─────────────────────────────────────────────────┘
```

