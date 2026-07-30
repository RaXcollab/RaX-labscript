#Post-shot analysis code. Adjusted from Lyse website 
# example, "Single shot analysis with global file opening"

import lyse
import numpy as np
import matplotlib.pyplot as plt
import os
import h5py

df = lyse.data()
h5_path = df.filepath.iloc[-1]

# Extract the directory (folder) from the full file path
folder_path = os.path.dirname(h5_path)

# # Get a dictionary of the global variables used in this shot
# run_globals = run.get_globals()
# print(run_globals)
image_data_nuvu = np.zeros([512, 512])
pixel_sum_array=[]
count = 0
# print(os.listdir(folder_path))

for filename in sorted(os.listdir(folder_path)):
    if not filename.endswith('.h5'):
        continue
    file_path = os.path.join(folder_path, filename)
    with h5py.File(file_path, 'r') as file:
        has_result = ('results/analysis_opencell2' in file
                      and 'pixel_sum' in file['results/analysis_opencell2'].attrs)
    if has_result:
        df2 = lyse.data(file_path)
        pixel_sum_array.append(df2["analysis_opencell2", "pixel_sum"] * 1000)
    else:
        print("This file does not have pixel_sum:", file_path)

        

# image_data_nuvu = image_data_nuvu/count
# plt.clf()
# plt.figure(2, figsize=(10, 4))
# # Second subplot (top-right) - fluorescence image
# pixel_size = 16e-3  # [mm]
# plt.imshow(image_data_nuvu, extent=[0, 512 * pixel_size, 0, 512 * pixel_size], cmap='magma')
# plt.colorbar(label='Intensity')
# plt.title('Averaged Fluorescence Image', fontsize=16)
# plt.xlabel('x [mm]', fontsize=16)
# plt.ylabel('y [mm]', fontsize=16)



# df2 = lyse.data(h5_path)
# pixel_sum= df2["analysis", "pixel_sum"]
# print(np.shape(pixel_sum))

plt.figure(3, figsize=(10, 4))
pic_array = len(pixel_sum_array)
plt.plot(np.arange(pic_array), pixel_sum_array)
plt.title('Sum of Pixels', fontsize=16)
plt.xlabel('Pic number', fontsize=16)
plt.ylabel('Pixel Sum (x1000)', fontsize=16)
# # get global variable
# global_dict = run.get_globals()

# integrated_signal = df["analysis", "BaF_abs integrated"]
# integrated_signal_err = df["analysis", "BaF_abs integrated err"]
