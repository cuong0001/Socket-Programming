import os

def make_testdata():
    print("Creating 0 byte file...")
    with open ("testdata/zero.bin", "wb") as f:
        pass

    print("Creating 512 byte file...")
    with open ("testdata/512b.bin", "wb") as f:
        f.write(b"A" * 512)

    print("Creating 4096 byte file...")
    with open("testdata/4096b.bin", "wb") as f:
        f.write(b"B" * 4096)

    print("Creating 4097 byte file...")
    with open("testdata/4097b.bin", "wb") as f:
        f.write(b"C" * 4097)
    
    print("Creatin 10MB file...")
    with open("testdata/10mb.bin", "wb") as f:
        chunk = b"D" * 4096
        num_loops = (10 * 1024 * 1024) // 4096
        for _ in range(num_loops):
            f.write(chunk)

    print("Creating binary file...")
    with open("testdata/binary.bin", "wb") as f:
        all_bytes = bytes(range(256))
        f.write(all_bytes * 100)
    
    print("Creating 150MB file...")
    with open("testdata/150mb.bin", "wb") as f:
        chunk = b"E" * 4096
        num_loops = (150 * 1024 * 1024) // 4096
        for _ in range(num_loops):
            f.write(chunk)
            
    print("All 7 test files created successfully.")

if __name__ == "__main__":
    make_testdata()
    