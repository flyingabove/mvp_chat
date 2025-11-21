<?php
declare(strict_types=1);
const OPENAI_API_KEY = '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';
const OPENAI_MODEL   = 'gpt-4o-mini';
const MAX_TOKENS     = 512;
const TEMPERATURE    = 0.8;
const MEMORY_TURNS   = 18;
const GAME_TITLE     = 'storieschat.ai (beta)';
const START_LOCATION = 'Nonhyeon-dong officetel';
const START_MINUTE   = 0;
const MINS_PER_WORD  = 1.0/4;
const BASE_TURN_MINS = 1;
const TRAVEL_MINS    = 15;
const REL_MIN = -5;
const REL_MAX =  5;
const REL_START = 0;
const EMOTION_START = 'wary, exhausted';
