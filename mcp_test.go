package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestReadHandler(t *testing.T) {
	// 1. Setup temporary workspace and dummy file
	tempDir := t.TempDir()
	testFile := filepath.Join(tempDir, "test.txt")
	os.WriteFile(testFile, []byte("secure data"), 0644)

	// 2. Open the temporary directory as an os.Root jail
	rootDir, err := os.OpenRoot(tempDir)
	if err != nil {
		t.Fatalf("Failed to open root for test: %v", err)
	}
	defer rootDir.Close()

	// 3. Initialize the router with the test root and token
	testToken := "test-token-123"
	mux := setupRouter(rootDir, testToken)

	// 4. Create a simulated request
	req := httptest.NewRequest(http.MethodGet, "/read?path=test.txt", nil)
	req.Header.Set("Authorization", "Bearer "+testToken)

	// 5. Record the response directly from the mux
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	// 6. Assertions
	if w.Code != http.StatusOK {
		t.Fatalf("Expected status 200, got %d", w.Code)
	}
	if w.Body.String() != "secure data" {
		t.Fatalf("Expected 'secure data', got '%s'", w.Body.String())
	}
}
