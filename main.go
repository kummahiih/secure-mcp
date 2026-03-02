package main

import (
	"crypto/subtle"
	"crypto/tls"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
)

// setupRouter isolates the routing logic so it can be tested independently
func setupRouter(rootDir *os.Root, token string) *http.ServeMux {
	mux := http.NewServeMux()

	mux.HandleFunc("/read", func(w http.ResponseWriter, r *http.Request) {
		if !verifyToken(r, token) {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}

		targetPath := r.URL.Query().Get("path")

		log.Printf("Received request for %s", targetPath)

		file, err := rootDir.Open(targetPath)
		if err != nil {
			http.Error(w, "Access denied or file not found", http.StatusNotFound)
			return
		}
		defer file.Close()

		// 2. Read the content into a byte slice
		// Using io.ReadAll is fine for typical workspace files
		data, err := io.ReadAll(file)
		if err != nil {
			log.Printf("Read error: %v", err)
			http.Error(w, "Error reading file", http.StatusInternalServerError)
			return
		}

		// 1. Log the content for your own sanity
		log.Printf("FILE_SUCCESS: Sending raw content: %s", string(data))

		// 2. Set as plain text so the LLM sees it as a direct message
		w.Header().Set("Content-Type", "text/plain; charset=utf-8")

		// 3. SET STATUS CODE SECOND
		w.WriteHeader(http.StatusOK)

		// 3. Write the raw bytes directly to the response
		w.Write(data)
	})

	return mux
}

func verifyToken(r *http.Request, expectedToken string) bool {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		return false
	}

	parts := strings.SplitN(authHeader, " ", 2)
	if len(parts) != 2 || parts[0] != "Bearer" {
		return false
	}

	expectedBytes := []byte(expectedToken)
	providedBytes := []byte(parts[1])

	// ConstantTimeCompare requires equal lengths
	if len(expectedBytes) != len(providedBytes) {
		return false
	}

	return subtle.ConstantTimeCompare(providedBytes, expectedBytes) == 1
}

func main() {
	token := os.Getenv("MCP_API_TOKEN")
	if token == "" {
		log.Fatal("MCP_API_TOKEN is required")
	}

	rootDir, err := os.OpenRoot("/workspace")
	if err != nil {
		log.Fatalf("Failed to open root workspace: %v", err)
	}
	defer rootDir.Close()

	// Mount the isolated router
	mux := setupRouter(rootDir, token)

	server := &http.Server{
		Addr:    ":8443",
		Handler: mux,
		TLSConfig: &tls.Config{
			MinVersion: tls.VersionTLS12,
		},
	}

	log.Println("MCP Server listening on :8443 with TLS")
	log.Fatal(server.ListenAndServeTLS("/certs/mcp.crt", "/certs/mcp.key"))
}
