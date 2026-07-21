--[[
    Best BiS Tooltip TBC (v2.7)
    Показывает BiS-статус предмета в тултипе для всех 9 классов TBC.
    Ключи спеков: {spec}_{class} (fire_mage, restoration_druid и т.д.)
--]]

local addonName, addonTable = ...


-- ---------------------------------------------------------------------------
-- Слоты экипировки
-- ---------------------------------------------------------------------------
local ValidEquipLocs = {
    ["INVTYPE_HEAD"] = true, ["INVTYPE_NECK"] = true, ["INVTYPE_SHOULDER"] = true,
    ["INVTYPE_BODY"] = true, ["INVTYPE_CHEST"] = true, ["INVTYPE_ROBE"] = true,
    ["INVTYPE_WAIST"] = true, ["INVTYPE_LEGS"] = true, ["INVTYPE_FEET"] = true,
    ["INVTYPE_WRIST"] = true, ["INVTYPE_HAND"] = true, ["INVTYPE_FINGER"] = true,
    ["INVTYPE_TRINKET"] = true, ["INVTYPE_CLOAK"] = true, ["INVTYPE_WEAPON"] = true,
    ["INVTYPE_SHIELD"] = true, ["INVTYPE_2HWEAPON"] = true, ["INVTYPE_WEAPONMAINHAND"] = true,
    ["INVTYPE_WEAPONOFFHAND"] = true, ["INVTYPE_HOLDABLE"] = true, ["INVTYPE_RANGED"] = true,
    ["INVTYPE_THROWN"] = true, ["INVTYPE_RANGEDRIGHT"] = true, ["INVTYPE_RELIC"] = true,
    ["INVTYPE_TABARD"] = true,
}

local function IsEquippable(itemID)
    if not itemID then return false end
    local _, _, _, _, _, _, _, _, equipLoc = GetItemInfo(itemID)
    return equipLoc and ValidEquipLocs[equipLoc] == true
end

-- Возвращает суффиксы оружия для строки тултипа:
-- nil если не двуручка или не воин, "Two-Hander" если двуручка, "Two-Hander - Sword Specced" если двуручный меч
-- Суффикс показывается только для воинов — для остальных классов двуручник не нишевая опция
local function GetWeaponSuffixes(itemID, specKey)
    if not itemID then return nil end
    if not specKey or not specKey:find("warrior") then return nil end
    local _, _, _, _, _, _, subClass, _, equipLoc = GetItemInfo(itemID)
    if equipLoc ~= "INVTYPE_2HWEAPON" then return nil end
    if subClass == "Swords" then
        return "Two-Hander - Sword Specced"
    end
    return "Two-Hander"
end

-- ---------------------------------------------------------------------------
-- Спеки по классам — порядок определяет порядок вывода при Shift
-- ---------------------------------------------------------------------------
local ClassSpecs = {
    ["MAGE"]    = { "arcane_mage", "fire_mage", "frost_mage" },
    ["PRIEST"]  = { "shadow_priest", "holy_priest" },
    ["WARLOCK"] = { "affliction_warlock", "demonology_warlock", "destruction_warlock" },
    ["DRUID"]   = { "balance_druid", "feral_druid", "feral_tank_druid", "restoration_druid" },
    ["SHAMAN"]  = { "elemental_shaman", "enhancement_shaman", "restoration_shaman" },
    ["HUNTER"]  = { "beastmastery_hunter", "survival_hunter", "marksmanship_hunter" },
    ["ROGUE"]   = { "combat_rogue" },
    ["WARRIOR"] = { "fury_warrior", "arms_warrior", "protection_warrior" },
    ["PALADIN"] = { "holy_paladin", "protection_paladin", "retribution_paladin" },
}

-- Названия спеков для вывода (без класса — класс и так понятен)
local SpecNames = {
    ["arcane_mage"]          = "Arcane",
    ["fire_mage"]            = "Fire",
    ["frost_mage"]           = "Frost",
    ["shadow_priest"]        = "Shadow",
    ["holy_priest"]          = "Holy",
    ["affliction_warlock"]   = "Affliction",
    ["demonology_warlock"]   = "Demonology",
    ["destruction_warlock"]  = "Destruction",
    ["balance_druid"]        = "Balance",
    ["feral_druid"]          = "Feral Cat",
    ["feral_tank_druid"]     = "Feral Tank",
    ["restoration_druid"]    = "Restoration",
    ["elemental_shaman"]     = "Elemental",
    ["enhancement_shaman"]   = "Enhancement",
    ["restoration_shaman"]   = "Restoration",
    ["beastmastery_hunter"]   = "Beast Mastery",
    ["survival_hunter"]       = "Survival",
    ["marksmanship_hunter"]   = "Marksmanship",
    ["combat_rogue"]         = "Combat",
    ["arms_warrior"]         = "Arms",
    ["fury_warrior"]         = "Fury",
    ["protection_warrior"]   = "Protection",
    ["holy_paladin"]         = "Holy",
    ["protection_paladin"]   = "Protection",
    ["retribution_paladin"]  = "Retribution",
}

-- Цвета спеков при выводе через Shift
local SpecColors = {
    -- Маг
    ["arcane_mage"]          = "|cFFD680FF",  -- как Close to BiS
    ["fire_mage"]            = "|cFFFA5523",  -- огненно-красный
    ["frost_mage"]           = "|cFF3FC7EB",  -- ледяной голубой
    -- Прист
    ["shadow_priest"]        = "|cFFB388FF",  -- лавандовый светлый
    ["holy_priest"]          = "|cFFFFF0AA",  -- тёплый жёлто-белый
    -- Варлок
    ["affliction_warlock"]   = "|cFFB388FF",  -- как шадоу прист, лавандовый
    ["demonology_warlock"]   = "|cFF55AA44",  -- демонический зелёный
    ["destruction_warlock"]  = "|cFFFA5523",  -- как фаер маг, огненный
    -- Друид
    ["balance_druid"]        = "|cFFCC99FF",  -- лавандовый
    ["feral_druid"]          = "|cFFFF7D0A",  -- классовый оранжевый
    ["feral_tank_druid"]     = "|cFFFF7D0A",  -- классовый оранжевый
    ["restoration_druid"]    = "|cFF4DFFB4",  -- мятно-зелёный
    -- Шаман
    ["elemental_shaman"]     = "|cFF4488FF",  -- насыщенный синий
    ["enhancement_shaman"]   = "|cFFFFF0AA",  -- как холи прист, тёплый жёлто-белый
    ["restoration_shaman"]   = "|cFF4DCCAA",  -- зелёный с оттенком синего
    -- Хантер
    ["beastmastery_hunter"]   = "|cFFFFD966",  -- жёлтый
    ["survival_hunter"]       = "|cFF80FF80",  -- как Not on BiS Lists
    ["marksmanship_hunter"]   = "|cFF7ABFFF",  -- стальной голубой (как Protection Paladin)
    -- Разбойник
    ["combat_rogue"]         = "|cFFFFF569",  -- классовый жёлтый
    -- Воин
    ["arms_warrior"]         = "|cFF78AAFF",  -- небесно-голубой светлый
    ["fury_warrior"]         = "|cFFFF6655",  -- кровавый красный, читаемый
    ["protection_warrior"]   = "|cFFC79C6E",  -- классовый светло-коричневый
    -- Паладин
    ["holy_paladin"]         = "|cFFF58CBA",  -- классовый розовый
    ["protection_paladin"]   = "|cFF7ABFFF",  -- стальной голубой (доспех)
    ["retribution_paladin"]  = "|cFFB388FF",  -- лавандово-фиолетовый
}

-- ---------------------------------------------------------------------------
-- Определение текущего спека
-- ---------------------------------------------------------------------------
local function GetCurrentPlayerSpec(playerClass)
    local _, _, _, _, p1 = GetTalentTabInfo(1)
    local _, _, _, _, p2 = GetTalentTabInfo(2)
    local _, _, _, _, p3 = GetTalentTabInfo(3)
    p1, p2, p3 = p1 or 0, p2 or 0, p3 or 0

    if playerClass == "MAGE" then
        if p1 >= p2 and p1 >= p3 then return "arcane_mage"
        elseif p2 >= p1 and p2 >= p3 then return "fire_mage"
        else return "frost_mage" end

    elseif playerClass == "PRIEST" then
        if p3 >= p1 and p3 >= p2 then return "shadow_priest"
        else return "holy_priest" end

    elseif playerClass == "WARLOCK" then
        if p1 >= p2 and p1 >= p3 then return "affliction_warlock"
        elseif p2 >= p1 and p2 >= p3 then return "demonology_warlock"
        else return "destruction_warlock" end

    elseif playerClass == "DRUID" then
        if p1 >= p2 and p1 >= p3 then return "balance_druid"
        elseif p3 >= p1 and p3 >= p2 then return "restoration_druid"
        else return "feral_druid" end

    elseif playerClass == "SHAMAN" then
        if p1 >= p2 and p1 >= p3 then return "elemental_shaman"
        elseif p2 >= p1 and p2 >= p3 then return "enhancement_shaman"
        else return "restoration_shaman" end

    elseif playerClass == "HUNTER" then
        if p1 >= p2 and p1 >= p3 then return "beastmastery_hunter"
        elseif p2 >= p1 and p2 >= p3 then return "marksmanship_hunter"
        else return "survival_hunter" end

    elseif playerClass == "ROGUE" then
        return "combat_rogue"

    elseif playerClass == "WARRIOR" then
        if p3 >= p1 and p3 >= p2 then return "protection_warrior"
        elseif p2 >= p1 then return "fury_warrior"
        else return "arms_warrior" end

    elseif playerClass == "PALADIN" then
        if p1 >= p2 and p1 >= p3 then return "holy_paladin"
        elseif p2 >= p1 and p2 >= p3 then return "protection_paladin"
        else return "retribution_paladin" end
    end

    return nil
end


-- ---------------------------------------------------------------------------
-- Цвета статусов
-- ---------------------------------------------------------------------------
local colorFireDestro   = "|cFFFF3333"   -- красный
local colorShadowDestro = "|cFFAA44FF"   -- зловещий фиолетовый

-- Разбирает статус на базовую часть и Destro-суффикс
-- Возвращает baseStatus, destroTag (или nil)
local function SplitDestroSuffix(status)
    if not status then return status, nil end
    if status:find(" %- Fire Destro$") then
        return status:sub(1, -(" - Fire Destro"):len() - 1), "Fire Destro"
    elseif status:find(" %- Shadow Destro$") then
        return status:sub(1, -(" - Shadow Destro"):len() - 1), "Shadow Destro"
    end
    return status, nil
end

local function GetColorAndText(status, equipLoc)
    local rO = "|cFFFF8000"   -- Absolute BiS / BiS #2
    local rP = "|cFFD680FF"   -- Close to BiS / Hit variants
    local rB = "|cFF5C9DFF"   -- Sub-BiS (Optional)
    local rM = "|cFF00FF96"   -- Sub-BiS Further Options / Alternative

    if not status then return rB, "" end
    -- Отрезаем Destro-суффикс перед определением цвета
    local base = status:gsub(" %- Fire Destro$", ""):gsub(" %- Shadow Destro$", "")
    local s = base:lower()

    -- Для колец и тринкетов: переопределяем иерархию статусов
    local isRingOrTrinket = (equipLoc == "INVTYPE_FINGER" or equipLoc == "INVTYPE_TRINKET")
    if isRingOrTrinket then
        if s == "close to bis" then
            return rP, "BiS #2"
        elseif s == "third place" then
            return rP, "Close to BiS"
        end
    end

    if s:find("^bis #2") then
        return rP, status
    elseif s:find("absolute bis") or s:find("jewelcrafting") or s:find("against demons") or s:find("second bis") then
        return rO, status
    elseif s:find("close to bis") then
        return rP, status
    elseif s:find("sub%-bis further") then
        return rM, status
    elseif s:find("sub%-bis") then
        return rB, status
    elseif s:find("need hit") or s:find("best threat") or s:find("if you need") then
        return rP, status
    elseif s:find("alternative") then
        return rM, status
    end

    return rB, status
end

-- Строит строку тултипа с фазой и опциональным Destro-суффиксом нужного цвета
-- Формат: "Base - Phase - Suffix - WeaponSuffix - Destro"
local function FormatStatusLine(status, phaseName, indent, itemID, specKey)
    indent = indent or ""
    local base, destroTag = SplitDestroSuffix(status)
    local _, _, _, _, _, _, _, _, equipLoc = GetItemInfo(itemID)
    local c, overrideLabel = GetColorAndText(status, equipLoc)

    -- Вычленяем суффикс в скобках: "Close to BiS (Best Threat)" -> base="Close to BiS", suffix="Best Threat"
    -- Или текстовый суффикс через пробел: "Sub-BiS Threat Alternative" -> base="Sub-BiS", suffix="Threat Alternative"
    local coreStatus, inlineSuffix = base, nil

    -- Скобки остаются частью coreStatus — фаза добавляется после них
    local parenSuffix = base:match("%((.-)%)$")
    if not parenSuffix then
        -- Шаг 1: сначала снимаем тире-суффиксы (warrior weapon suffixes и т.п.)
        -- Может быть несколько: "Absolute BiS - Two-Hander - Sword Specced"
        local dashSuffixes = {
            "Main Hand", "Off Hand",
            "Orc Off-Hand", "Human Off-Hand",
        }
        local foundDashSuffixes = {}
        local remaining = base
        local changed = true
        while changed do
            changed = false
            for _, sfx in ipairs(dashSuffixes) do
                local pat = " %- " .. sfx:gsub("%-", "%%-") .. "$"
                if remaining:find(pat) then
                    remaining = remaining:gsub(pat, "")
                    table.insert(foundDashSuffixes, 1, sfx)
                    changed = true
                    break
                end
            end
        end
        if #foundDashSuffixes > 0 then
            coreStatus = remaining
            inlineSuffix = table.concat(foundDashSuffixes, " - ")
        end

        -- Шаг 2: текстовые суффиксы через пробел (только если нет тире-суффикса)
        if not inlineSuffix then
            local textSuffixes = {
                "Threat Alternative", "Mitigation Alternative", "Crafted Alternative",
                "Further Options", "if you need Hit", "Scryers only",
            }
            local suffixDisplay = {
                ["if you need Hit"] = "If you need Hit",
                ["Scryers only"]    = "Scryers Only",
            }
            for _, sfx in ipairs(textSuffixes) do
                if base:find(sfx, 1, true) then
                    coreStatus = base:gsub("%s*" .. sfx:gsub("%-", "%%-") .. "$", ""):gsub("%s+$", "")
                    inlineSuffix = suffixDisplay[sfx] or sfx
                    break
                end
            end
        end
    end

    -- Если GetColorAndText вернул overrideLabel (например "BiS #2") — используем его
    if overrideLabel and overrideLabel ~= status then
        coreStatus = overrideLabel
        inlineSuffix = nil
    end

    local line = c .. indent .. coreStatus .. " - " .. phaseName
    if inlineSuffix then
        line = line .. " - " .. inlineSuffix
    end

    -- Суффиксы двуручного оружия: "Two-Hander" и "Sword Specced" — определяем по типу предмета
    local weaponSuffix = GetWeaponSuffixes(itemID, specKey)
    if weaponSuffix then
        line = line .. " - " .. weaponSuffix
    end

    if destroTag == "Fire Destro" then
        line = line .. " " .. c .. "-|r " .. colorFireDestro .. "Fire Destro|r"
    elseif destroTag == "Shadow Destro" then
        line = line .. " " .. c .. "-|r " .. colorShadowDestro .. "Shadow Destro|r"
    else
        line = line .. "|r"
    end
    return line
end

-- ---------------------------------------------------------------------------
-- Основная логика тултипа
-- ---------------------------------------------------------------------------
local PHASES = { {"p2", "Phase 2 (TK + SSC)"}, {"p1", "Phase 1"}, {"pre", "Pre-Raid"} }
local rankNotViable = "|cFF80FF80"
local dungeonBlue   = "|cFF00C0FF"

local function ProcessTooltipUpdate(tooltip)
    if not tooltip or not tooltip.GetItem then return end
    local _, link = tooltip:GetItem()
    if not link then return end

    local itemID = GetItemInfoInstant(link)
    if not IsEquippable(itemID) then return end

    local _, pClass = UnitClass("player")
    local specsToProcess = ClassSpecs[pClass]
    if not specsToProcess then return end

    local currentSpec = GetCurrentPlayerSpec(pClass)

    local hasItemInDatabase = false
    local itemData = {}
    if BestBisListData then
        local success, result = pcall(function() return BestBisListData[itemID] end)
        if success and result then
            itemData = result
            for _, specKey in ipairs(specsToProcess) do
                if itemData[specKey] then
                    hasItemInDatabase = true
                    break
                end
            end
        end
    end

    if not hasItemInDatabase then
        if IsShiftKeyDown() then
            local isFeral = pClass == "DRUID" and (currentSpec == "feral_druid" or currentSpec == "feral_tank_druid")
            for _, specKey in ipairs(specsToProcess) do
                local isFeralSpec = (specKey == "feral_druid" or specKey == "feral_tank_druid")
                local shouldSkip = (specKey == currentSpec) or (isFeral and isFeralSpec)
                if not shouldSkip then
                    local sc = SpecColors[specKey] or "|cFFFFFFFF"
                    tooltip:AddLine(sc .. (SpecNames[specKey] or specKey) .. ": " .. rankNotViable .. "Not on BiS Lists|r")
                end
            end
        else
            if #specsToProcess > 1 then
                tooltip:AddDoubleLine(rankNotViable .. "Not on BiS Lists|r", dungeonBlue .. "Press Shift for All Specs|r")
            else
                tooltip:AddLine(rankNotViable .. "Not on BiS Lists|r")
            end
        end
        tooltip:Show()
        return
    end

    if IsShiftKeyDown() then
        -- Показываем все спеки кроме текущего
        -- Для feral друида (DPS или Tank) — скрываем оба feral спека, показываем Balance и Resto
        local isFeral = pClass == "DRUID" and (currentSpec == "feral_druid" or currentSpec == "feral_tank_druid")
        local needSeparator = false
        for _, specKey in ipairs(specsToProcess) do
            local isFeralSpec = (specKey == "feral_druid" or specKey == "feral_tank_druid")
            local shouldSkip = (specKey == currentSpec) or (isFeral and isFeralSpec)
            if not shouldSkip then
                if needSeparator then tooltip:AddLine(" ") end
                local sc = SpecColors[specKey] or "|cFFFFFFFF"
                tooltip:AddLine(sc .. (SpecNames[specKey] or specKey) .. ":|r")
                local specHasData = false
                if itemData[specKey] then
                    for _, phaseInfo in ipairs(PHASES) do
                        local pKey, pName = phaseInfo[1], phaseInfo[2]
                        local status = itemData[specKey][pKey]
                        if status and status ~= "" then
                            tooltip:AddLine(FormatStatusLine(status, pName, "  ", itemID, specKey))
                            specHasData = true
                        end
                    end
                end
                if not specHasData then
                    tooltip:AddLine("  " .. rankNotViable .. "Not on BiS Lists|r")
                end
                needSeparator = true
            end
        end
    else
        -- Определяем что показывать без шифта
        local specsForDisplay = {}
        local showSpecHeader = false  -- показывать ли заголовок спека

        if pClass == "DRUID" and (currentSpec == "feral_druid" or currentSpec == "feral_tank_druid") then
            -- Feral друид: всегда показываем оба feral спека с заголовками
            specsForDisplay = { "feral_druid", "feral_tank_druid" }
            showSpecHeader = true
        elseif #specsToProcess == 1 then
            -- Класс с одним viable спеком (разбойник): данные всегда из этого спека
            local viableSpec = specsToProcess[1]
            specsForDisplay = { viableSpec }
            -- Заголовок только если игрок не в этом спеке
            showSpecHeader = (currentSpec ~= viableSpec)
        else
            -- Обычный случай: показываем текущий спек без заголовка
            specsForDisplay = { currentSpec }
            showSpecHeader = false
        end

        local anyDisplayed = false
        local needSeparator = false
        for _, displaySpec in ipairs(specsForDisplay) do
            if not displaySpec then break end
            if needSeparator then tooltip:AddLine(" ") end
            local indent = ""
            if showSpecHeader then
                local sc = SpecColors[displaySpec] or "|cFFFFFFFF"
                tooltip:AddLine(sc .. (SpecNames[displaySpec] or displaySpec) .. ":|r")
                indent = "  "
            end
            if itemData[displaySpec] then
                local specHasAnyPhase = false
                for _, phaseInfo in ipairs(PHASES) do
                    local pKey, pName = phaseInfo[1], phaseInfo[2]
                    local status = itemData[displaySpec][pKey]
                    if status and status ~= "" then
                        tooltip:AddLine(FormatStatusLine(status, pName, indent, itemID, displaySpec))
                        specHasAnyPhase = true
                    end
                end
                if not specHasAnyPhase then
                    tooltip:AddLine(indent .. rankNotViable .. "Not on BiS Lists|r")
                end
                anyDisplayed = true
            else
                tooltip:AddLine(indent .. rankNotViable .. "Not on BiS Lists|r")
                anyDisplayed = true
            end
            needSeparator = true
        end

        -- Считаем сколько спеков будет в шифт-меню
        local isFeral = pClass == "DRUID" and (currentSpec == "feral_druid" or currentSpec == "feral_tank_druid")
        local shiftSpecCount = 0
        for _, specKey in ipairs(specsToProcess) do
            local isFeralSpec = (specKey == "feral_druid" or specKey == "feral_tank_druid")
            if specKey ~= currentSpec and not (isFeral and isFeralSpec) then
                shiftSpecCount = shiftSpecCount + 1
            end
        end

        if not anyDisplayed then
            if shiftSpecCount > 0 then
                tooltip:AddDoubleLine(rankNotViable .. "Not on BiS Lists|r", dungeonBlue .. "Press Shift for All Specs|r")
            else
                tooltip:AddLine(rankNotViable .. "Not on BiS Lists|r")
            end
        elseif shiftSpecCount > 0 then
            tooltip:AddLine(" ")
            tooltip:AddDoubleLine(" ", dungeonBlue .. "Press Shift for All Specs|r")
        end
    end

    tooltip:Show()
end

-- ---------------------------------------------------------------------------
-- Хуки тултипов
-- ---------------------------------------------------------------------------
GameTooltip:HookScript("OnTooltipSetItem", ProcessTooltipUpdate)
ItemRefTooltip:HookScript("OnTooltipSetItem", ProcessTooltipUpdate)
ShoppingTooltip1:HookScript("OnTooltipSetItem", ProcessTooltipUpdate)
ShoppingTooltip2:HookScript("OnTooltipSetItem", ProcessTooltipUpdate)

-- ---------------------------------------------------------------------------
-- Обновление при зажатии/отпускании Shift
-- ---------------------------------------------------------------------------
local refreshFrame = CreateFrame("Frame")
refreshFrame:RegisterEvent("MODIFIER_STATE_CHANGED")
refreshFrame:SetScript("OnEvent", function(self, event, key, state)
    if key == "LSHIFT" or key == "RSHIFT" then
        local tooltips = { GameTooltip, ItemRefTooltip, ShoppingTooltip1, ShoppingTooltip2 }
        for _, tt in ipairs(tooltips) do
            if tt and tt:IsShown() and tt.GetItem then
                local owner = tt:GetOwner()
                local _, link = tt:GetItem()
                if owner and link then
                    tt:SetOwner(owner, "ANCHOR_NONE")
                    tt:SetHyperlink(link)
                    tt:Show()
                end
            end
        end
    end
end)

-- ---------------------------------------------------------------------------
-- PaperDoll — вещи на персонаже
-- ---------------------------------------------------------------------------
hooksecurefunc("PaperDollItemSlotButton_OnEnter", function(self)
    local slotID = self:GetID()
    local itemLink = GetInventoryItemLink("player", slotID)
    if not itemLink then return end
    local itemID = GetItemInfoInstant(itemLink)
    if not IsEquippable(itemID) then return end

    local _, pClass = UnitClass("player")
    local specsToProcess = ClassSpecs[pClass]
    if not specsToProcess then return end

    local hasItemInDatabase = false
    local itemData = {}
    if BestBisListData then
        local success, result = pcall(function() return BestBisListData[itemID] end)
        if success and result then
            itemData = result
            for _, specKey in ipairs(specsToProcess) do
                if itemData[specKey] then hasItemInDatabase = true; break end
            end
        end
    end

    if not hasItemInDatabase then
        if IsShiftKeyDown() then
            for _, specKey in ipairs(specsToProcess) do
                local sc = SpecColors[specKey] or "|cFFFFFFFF"
                GameTooltip:AddLine(sc .. (SpecNames[specKey] or specKey) .. ": " .. rankNotViable .. "Not on BiS Lists|r")
            end
        else
            if #specsToProcess > 1 then
                GameTooltip:AddDoubleLine(rankNotViable .. "Not on BiS Lists|r", dungeonBlue .. "Press Shift for All Specs|r")
            else
                GameTooltip:AddLine(rankNotViable .. "Not on BiS Lists|r")
            end
        end
        GameTooltip:Show()
    end
end)
