package main

import (
	"encoding/gob"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

type HistoryData struct {
	LastUsed time.Time
	Amount   int
}

type History struct {
	Data map[string]map[string]*HistoryData
}

func main() {
	home, _ := os.UserHomeDir()
	
	// We check both standard desktop apps and the runner (which often handles keybinds/direct commands)
	histories := []string{
		".cache/elephant/desktopapplications_history.gob",
		".cache/elephant/runner_history.gob",
		".cache/elephant/menus_history.gob",
	}

	mergedData := make(map[string]map[string]*HistoryData)

	for _, relPath := range histories {
		path := filepath.Join(home, relPath)
		file, err := os.Open(path)
		if err != nil {
			continue
		}
		
		var h History
		decoder := gob.NewDecoder(file)
		err = decoder.Decode(&h)
		file.Close()
		
		if err != nil {
			continue
		}

		for term, apps := range h.Data {
			if _, ok := mergedData[term]; !ok {
				mergedData[term] = make(map[string]*HistoryData)
			}
			for app, stats := range apps {
				if existing, ok := mergedData[term][app]; ok {
					existing.Amount += stats.Amount
					if stats.LastUsed.After(existing.LastUsed) {
						existing.LastUsed = stats.LastUsed
					}
				} else {
					mergedData[term][app] = &HistoryData{
						LastUsed: stats.LastUsed,
						Amount:   stats.Amount,
					}
				}
			}
		}
	}

	jsonData, _ := json.MarshalIndent(mergedData, "", "  ")
	fmt.Println(string(jsonData))
}
