/**
 * Portal 1 Bot - Custom Server Plugin Example
 * This is an example of a Source SDK 2013 server plugin that extracts
 * structured 3D world data and exports it via TCP/JSON or shared memory.
 *
 * This is the MOST RELIABLE method to get game state without memory hacking.
 *
 * Build:
 * - Requires Source SDK 2013 (https://github.com/ValveSoftware/source-sdk-2013)
 * - Place this file in sp/src/game/server/portal/
 * - Add to server_hl2.vpc or create new project
 * - Compile as portal_bot.dll
 *
 * Usage:
 * - Put portal_bot.dll in portal/addons/
 * - In game console: plugin_load portal/addons/portal_bot
 * - Plugin will start HTTP server on localhost:27015 or write JSON to file
 */

#include "cbase.h"
#include "engine/iserverplugin.h"
#include "toolframework/ienginetool.h"
#include "eiface.h"
#include "igameevents.h"
#include "convar.h"
#include "tier1.h"
#include <winsock2.h>
#include <string>
#include <vector>
#include <sstream>

// Interfaces
IVEngineServer *engine = NULL;
IServerGameDLL *gamedll = NULL;
IServerGameEnts *gameents = NULL;
IGameEventManager2 *gameeventmanager = NULL;

// Global
CGlobalVars *gpGlobals = NULL;

// Plugin class
class CPortalBotPlugin : public IServerPluginCallbacks
{
public:
    CPortalBotPlugin();
    virtual bool Load(CreateInterfaceFn interfaceFactory, CreateInterfaceFn gameServerFactory);
    virtual void Unload();
    virtual void Pause() {}
    virtual void UnPause() {}
    virtual const char *GetPluginDescription() { return "Portal 1 Bot - GameState Provider v1.0"; }
    virtual void LevelInit(char const *pMapName);
    virtual void ServerActivate(edict_t *pEdictList, int edictCount, int clientMax);
    virtual void GameFrame(bool simulating);
    virtual void LevelShutdown() {}
    virtual void ClientActive(edict_t *pEntity) {}
    virtual void ClientDisconnect(edict_t *pEntity) {}
    virtual void ClientPutInServer(edict_t *pEntity, char const *playername) {}
    virtual void SetCommandClient(int index) {}
    virtual void ClientSettingsChanged(edict_t *pEdict) {}
    virtual PLUGIN_RESULT ClientConnect(bool *bAllowConnect, edict_t *pEntity, const char *pszName, const char *pszAddress, char *reject, int maxrejectlen);
    virtual PLUGIN_RESULT ClientCommand(edict_t *pEntity, const CCommand &args);
    virtual PLUGIN_RESULT NetworkIDValidated(const char *pszUserName, const char *pszNetworkID);
    virtual void OnQueryCvarValueFinished(QueryCvarCookie_t iCookie, edict_t *pPlayerEntity, EQueryCvarValueStatus eStatus, const char *pCvarName, const char *pCvarValue);
    virtual void OnEdictAllocated(edict_t *edict) {}
    virtual void OnEdictFreed(const edict_t *edict) {}

    // Custom methods
    void DumpGameState();
    void DumpEntities();
    void DumpPlayer();
    std::string GetEntityClassname(CBaseEntity *pEntity);
    void ExportJSON(const std::string &json);

private:
    bool m_bEnabled;
    float m_fLastDumpTime;
    int m_iDumpInterval; // ms
    SOCKET m_Socket;
};

CPortalBotPlugin g_PortalBotPlugin;
EXPOSE_SINGLE_INTERFACE_GLOBALVAR(CPortalBotPlugin, IServerPluginCallbacks, INTERFACEVERSION_ISERVERPLUGINCALLBACKS, g_PortalBotPlugin);

CPortalBotPlugin::CPortalBotPlugin() : m_bEnabled(true), m_fLastDumpTime(0), m_iDumpInterval(100)
{
}

bool CPortalBotPlugin::Load(CreateInterfaceFn interfaceFactory, CreateInterfaceFn gameServerFactory)
{
    // Get interfaces
    engine = (IVEngineServer*)interfaceFactory(INTERFACEVERSION_VENGINESERVER, NULL);
    gamedll = (IServerGameDLL*)gameServerFactory(INTERFACEVERSION_SERVERGAMEDLL, NULL);
    gameents = (IServerGameEnts*)gameServerFactory(INTERFACEVERSION_SERVERGAMEENTS, NULL);
    gameeventmanager = (IGameEventManager2*)interfaceFactory(INTERFACEVERSION_GAMEEVENTSMANAGER2, NULL);

    if (!engine || !gamedll || !gameents)
    {
        Warning("PortalBot: Failed to get interfaces\n");
        return false;
    }

    gpGlobals = gamedll->GetGlobalVars();

    // Initialize Winsock for TCP export
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2,2), &wsaData);

    // Create socket for JSON export (localhost:27015)
    m_Socket = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP); // UDP for simplicity

    ConVar_Register(0);

    Msg("PortalBot: Loaded successfully - GameState Provider active\n");
    Msg("PortalBot: Will export JSON to portal_bot_state.json and UDP localhost:27015\n");

    return true;
}

void CPortalBotPlugin::Unload()
{
    closesocket(m_Socket);
    WSACleanup();
    ConVar_Unregister();
}

void CPortalBotPlugin::LevelInit(char const *pMapName)
{
    Msg("PortalBot: LevelInit %s\n", pMapName);
}

void CPortalBotPlugin::ServerActivate(edict_t *pEdictList, int edictCount, int clientMax)
{
    Msg("PortalBot: ServerActivate\n");
}

void CPortalBotPlugin::GameFrame(bool simulating)
{
    if (!m_bEnabled || !simulating)
        return;

    float currentTime = gpGlobals->curtime;
    if ((currentTime - m_fLastDumpTime) * 1000.0f < m_iDumpInterval)
        return;

    m_fLastDumpTime = currentTime;
    DumpGameState();
}

PLUGIN_RESULT CPortalBotPlugin::ClientConnect(bool *bAllowConnect, edict_t *pEntity, const char *pszName, const char *pszAddress, char *reject, int maxrejectlen)
{
    return PLUGIN_CONTINUE;
}

PLUGIN_RESULT CPortalBotPlugin::ClientCommand(edict_t *pEntity, const CCommand &args)
{
    const char *cmd = args[0];
    if (Q_strcmp(cmd, "portal_bot_dump") == 0)
    {
        DumpGameState();
        return PLUGIN_STOP;
    }
    else if (Q_strcmp(cmd, "portal_bot_enable") == 0)
    {
        m_bEnabled = true;
        Msg("PortalBot: Enabled\n");
        return PLUGIN_STOP;
    }
    else if (Q_strcmp(cmd, "portal_bot_disable") == 0)
    {
        m_bEnabled = false;
        Msg("PortalBot: Disabled\n");
        return PLUGIN_STOP;
    }
    return PLUGIN_CONTINUE;
}

PLUGIN_RESULT CPortalBotPlugin::NetworkIDValidated(const char *pszUserName, const char *pszNetworkID)
{
    return PLUGIN_CONTINUE;
}

void CPortalBotPlugin::OnQueryCvarValueFinished(QueryCvarCookie_t iCookie, edict_t *pPlayerEntity, EQueryCvarValueStatus eStatus, const char *pCvarName, const char *pCvarValue)
{
}

std::string CPortalBotPlugin::GetEntityClassname(CBaseEntity *pEntity)
{
    if (!pEntity)
        return "null";
    return pEntity->GetClassname();
}

void CPortalBotPlugin::DumpPlayer()
{
    // Get local player (index 1)
    edict_t *pPlayerEdict = engine->PEntityOfEntIndex(1);
    if (!pPlayerEdict || pPlayerEdict->IsFree())
        return;

    CBaseEntity *pPlayer = gameents->EdictToBaseEntity(pPlayerEdict);
    if (!pPlayer)
        return;

    Vector origin = pPlayer->GetAbsOrigin();
    QAngle angles = pPlayer->GetAbsAngles();
    Vector velocity;
    pPlayer->GetVelocity(&velocity, NULL);

    // For CBasePlayer, need to cast
    // CBasePlayer *pBasePlayer = ToBasePlayer(pPlayer);
    // Vector viewOffset = pBasePlayer->GetViewOffset();
    // Vector eyePos = origin + viewOffset;
}

void CPortalBotPlugin::DumpEntities()
{
    // This will be part of DumpGameState
}

void CPortalBotPlugin::DumpGameState()
{
    // Build JSON with all entities
    std::stringstream ss;
    ss << "{\n";
    ss << "  \"timestamp\": " << gpGlobals->curtime << ",\n";
    ss << "  \"map\": \"" << gpGlobals->mapname.ToCStr() << "\",\n";

    // Player
    edict_t *pPlayerEdict = engine->PEntityOfEntIndex(1);
    if (pPlayerEdict && !pPlayerEdict->IsFree())
    {
        CBaseEntity *pPlayer = gameents->EdictToBaseEntity(pPlayerEdict);
        if (pPlayer)
        {
            Vector origin = pPlayer->GetAbsOrigin();
            QAngle angles = pPlayer->GetAbsAngles();
            Vector vel;
            pPlayer->GetVelocity(&vel, NULL);

            ss << "  \"player\": {\n";
            ss << "    \"pos\": [" << origin.x << ", " << origin.y << ", " << origin.z << "],\n";
            ss << "    \"ang\": [" << angles.x << ", " << angles.y << ", " << angles.z << "],\n";
            ss << "    \"vel\": [" << vel.x << ", " << vel.y << ", " << vel.z << "],\n";
            ss << "    \"alive\": true\n";
            ss << "  },\n";
        }
    }

    // Entities
    ss << "  \"entities\": [\n";
    bool first = true;
    for (int i = 0; i < gpGlobals->maxEntities; i++)
    {
        edict_t *pEdict = engine->PEntityOfEntIndex(i);
        if (!pEdict || pEdict->IsFree())
            continue;

        CBaseEntity *pEnt = gameents->EdictToBaseEntity(pEdict);
        if (!pEnt)
            continue;

        const char *classname = pEnt->GetClassname();
        // Filter interesting entities
        if (Q_strstr(classname, "prop_weighted_cube") ||
            Q_strstr(classname, "prop_physics") ||
            Q_strstr(classname, "prop_button") ||
            Q_strstr(classname, "func_door") ||
            Q_strstr(classname, "prop_portal") ||
            Q_strstr(classname, "npc_portal_turret") ||
            Q_strstr(classname, "player"))
        {
            Vector origin = pEnt->GetAbsOrigin();
            QAngle angles = pEnt->GetAbsAngles();
            Vector vel;
            pEnt->GetVelocity(&vel, NULL);

            if (!first) ss << ",\n";
            first = false;

            ss << "    {\n";
            ss << "      \"index\": " << i << ",\n";
            ss << "      \"classname\": \"" << classname << "\",\n";
            ss << "      \"origin\": [" << origin.x << ", " << origin.y << ", " << origin.z << "],\n";
            ss << "      \"angles\": [" << angles.x << ", " << angles.y << ", " << angles.z << "],\n";
            ss << "      \"velocity\": [" << vel.x << ", " << vel.y << ", " << vel.z << "]\n";
            ss << "    }";
        }
    }
    ss << "\n  ],\n";

    // Portals - specific
    ss << "  \"portals\": [\n";
    first = true;
    for (int i = 0; i < gpGlobals->maxEntities; i++)
    {
        edict_t *pEdict = engine->PEntityOfEntIndex(i);
        if (!pEdict || pEdict->IsFree()) continue;
        CBaseEntity *pEnt = gameents->EdictToBaseEntity(pEdict);
        if (!pEnt) continue;
        if (!Q_strstr(pEnt->GetClassname(), "prop_portal")) continue;

        Vector origin = pEnt->GetAbsOrigin();
        QAngle angles = pEnt->GetAbsAngles();

        // Read datamap properties for portal
        // m_bActivated, m_bIsPortal2, m_hLinkedPortal etc via datamap
        // For simplicity, we use offsets or SendProp

        if (!first) ss << ",\n";
        first = false;
        ss << "    {\n";
        ss << "      \"index\": " << i << ",\n";
        ss << "      \"origin\": [" << origin.x << ", " << origin.y << ", " << origin.z << "],\n";
        ss << "      \"angles\": [" << angles.x << ", " << angles.y << ", " << angles.z << "]\n";
        ss << "    }";
    }
    ss << "\n  ]\n";
    ss << "}\n";

    ExportJSON(ss.str());
}

void CPortalBotPlugin::ExportJSON(const std::string &json)
{
    // Write to file
    const char *filename = "portal_bot_state.json";
    FILE *f = fopen(filename, "w");
    if (f)
    {
        fwrite(json.c_str(), 1, json.length(), f);
        fclose(f);
    }

    // Send via UDP to localhost:27015 (Python bot can listen)
    sockaddr_in addr;
    addr.sin_family = AF_INET;
    addr.sin_port = htons(27015);
    addr.sin_addr.s_addr = inet_addr("127.0.0.1");

    sendto(m_Socket, json.c_str(), json.length(), 0, (sockaddr*)&addr, sizeof(addr));
}

/**
 * How to use from Python:
 *
 * import socket
 * import json
 *
 * sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
 * sock.bind(("127.0.0.1", 27015))
 * while True:
 *     data, addr = sock.recvfrom(65536)
 *     state = json.loads(data)
 *     print(state["player"]["pos"])
 *     # Update WorldModel
 */
